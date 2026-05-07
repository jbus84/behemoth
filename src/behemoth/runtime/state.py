"""DuckDB-backed tick-bar state manager.

Maintains a rolling buffer of tick bars per symbol and computes the exact
16-feature vector required by the Stage-03 CatBoost model.

The feature calculation is delegated to the canonical builder in
``src.behemoth.core.features`` -- this module is purely responsible for
storage, buffer management, and DataFrame assembly.

Design:
- In-memory DuckDB connection (no disk I/O for latency).
- Single ``tick_bars`` table partitioned by symbol.
- On ``compute_features()``, pulls the buffer into a small DataFrame
  and calls the shared builder for mathematical correctness.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from src.behemoth.core.features import (
    FeatureConfig,
    compute_features_from_bars,
    compute_regime_quantiles_from_bars,
)
from src.behemoth.core.schemas import (
    BarContext,
    BarPrices,
    IncomingTick,
    IncomingTickBar,
    ModelFeatures,
)
from src.behemoth.risk.account import ReservationState, ReservationStateMachine

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tick_bars (
    row_id INTEGER,
    symbol VARCHAR,
    bar_ticks INTEGER,
    ts TIMESTAMP WITH TIME ZONE,
    close_ts TIMESTAMP WITH TIME ZONE,
    open_bid DOUBLE,
    high_bid DOUBLE,
    low_bid DOUBLE,
    close_bid DOUBLE,
    spread DOUBLE,
    tick_volume DOUBLE,
    hl_first DOUBLE,
    hl_pos_frac DOUBLE,
    high_ask DOUBLE,
    close_ask DOUBLE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    event_ts TIMESTAMP WITH TIME ZONE,
    close_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    pred_prob DOUBLE,
    threshold DOUBLE,
    features_json VARCHAR,
    model_month VARCHAR,
    run_id VARCHAR
);

CREATE TABLE IF NOT EXISTS predict_evaluations (
    event_ts TIMESTAMP WITH TIME ZONE,
    close_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    pred_prob DOUBLE,
    threshold DOUBLE,
    preselected_exec INTEGER,
    selected_exec INTEGER,
    threshold_blocked BOOLEAN,
    threshold_block_reason VARCHAR,
    risk_blocked BOOLEAN,
    risk_block_reason VARCHAR,
    model_month VARCHAR,
    run_id VARCHAR
);

CREATE TABLE IF NOT EXISTS trades (
    internal_trade_id VARCHAR PRIMARY KEY,
    broker_pos_id VARCHAR,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    side VARCHAR,
    entry_price DOUBLE,
    entry_ts TIMESTAMP WITH TIME ZONE,
    entry_bar_id INTEGER,
    horizon_bars INTEGER,
    touch_bar_id INTEGER,
    exit_price DOUBLE,
    exit_ts TIMESTAMP WITH TIME ZONE,
    pnl_pips DOUBLE,
    status VARCHAR,
    run_id VARCHAR,
    reservation_id VARCHAR,
    entry_pred_prob DOUBLE,
    entry_threshold DOUBLE,
    entry_model_month VARCHAR,
    exit_bar_id INTEGER,
    close_reason VARCHAR,
    commission_ccy DOUBLE
);

CREATE TABLE IF NOT EXISTS account_risk_snapshots (
    snapshot_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    balance DOUBLE,
    equity DOUBLE
);

CREATE TABLE IF NOT EXISTS account_risk_reservations (
    reservation_id VARCHAR PRIMARY KEY,
    created_ts TIMESTAMP WITH TIME ZONE,
    updated_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    broker_pos_id VARCHAR,
    status VARCHAR,
    reserved_loss_ccy DOUBLE,
    barrier_pips DOUBLE,
    cap_pips DOUBLE,
    cost_est_pips DOUBLE,
    volume_units DOUBLE,
    side VARCHAR,
    source VARCHAR
);

CREATE TABLE IF NOT EXISTS account_risk_allocator_events (
    event_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    candidate_uid VARCHAR,
    status VARCHAR,
    block_reason VARCHAR,
    reserved_loss_ccy DOUBLE,
    requested_volume_units DOUBLE,
    pred_prob DOUBLE,
    threshold_exec DOUBLE,
    risk_rank_score DOUBLE,
    reservation_id VARCHAR
);

CREATE TABLE IF NOT EXISTS raw_ticks (
    tick_ts TIMESTAMP WITH TIME ZONE,
    ingest_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    bid DOUBLE,
    ask DOUBLE,
    spread DOUBLE,
    tick_volume DOUBLE,
    source VARCHAR,
    client_tick_seq BIGINT,
    run_id VARCHAR
);
"""

_INSERT_SQL = (
    "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_SQL = """
SELECT * FROM (
    SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid,
           close_bid, spread, tick_volume, hl_first, hl_pos_frac
    FROM tick_bars
    WHERE symbol = ? AND bar_ticks = ?
    ORDER BY row_id DESC
    LIMIT 600
) sub
ORDER BY row_id ASC
"""

_AUDIT_INSERT_SQL = """
INSERT INTO audit_logs (
    event_ts,
    close_ts,
    symbol,
    candidate_uid,
    pred_prob,
    threshold,
    features_json,
    model_month,
    run_id
) VALUES (
    CURRENT_TIMESTAMP,
    ?, ?, ?, ?, ?, ?, ?, ?
)
"""

_PREDICT_EVAL_INSERT_SQL = """
INSERT INTO predict_evaluations (
    event_ts,
    close_ts,
    symbol,
    candidate_uid,
    pred_prob,
    threshold,
    preselected_exec,
    selected_exec,
    threshold_blocked,
    threshold_block_reason,
    risk_blocked,
    risk_block_reason,
    model_month,
    run_id
) VALUES (
    CURRENT_TIMESTAMP,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
"""

_ACCOUNT_RISK_SNAPSHOT_INSERT_SQL = (
    "INSERT INTO account_risk_snapshots VALUES (?, ?, ?, ?)"
)

_ACCOUNT_RISK_RES_INSERT_SQL = (
    "INSERT INTO account_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_ACCOUNT_RISK_ALLOC_EVENT_INSERT_SQL = (
    "INSERT INTO account_risk_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_RAW_TICK_INSERT_SQL = (
    "INSERT INTO raw_ticks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


class StateManager:
    """Maintains rolling tick-bar state and produces CatBoost-ready features.

    Parameters
    ----------
    vol_window : int
        Window size for volatility / tick-rate / spread z-score normalizers.
        Default 96 (matches ``build_tick_velocity_dataset.py``).
    cost_window : int
        Window size for cost estimation (spread median + slippage proxy).
        Default 288 (matches ``build_tick_velocity_dataset.py``).
    """

    def __init__(
        self,
        vol_window: int = 96,
        cost_window: int = 288,
        *,
        persist_path: str | None = None,
    ) -> None:
        self._cfg = FeatureConfig(vol_window=int(vol_window), cost_window=int(cost_window))

        if persist_path:
            self._con = duckdb.connect(persist_path)
        else:
            self._con = duckdb.connect()

        self._con.execute(_CREATE_SQL)
        self._ensure_runtime_schema()
        self._row_counters: dict[str, int] = {}

        # Hydrate counters from persistent store to survive restarts
        res = self._con.execute(
            "SELECT symbol, bar_ticks, MAX(row_id) FROM tick_bars GROUP BY symbol, bar_ticks"
        ).fetchall()
        for r in res:
            if r[2] is not None:
                self._row_counters[f"{r[0].upper()}_{r[1]}"] = int(r[2]) + 1

    def _ensure_runtime_schema(self) -> None:
        """Ensure persisted runtime tables match the canonical explicit-bid schema."""
        self._migrate_tick_bars_table()
        self._ensure_table_column(
            table_name="audit_logs",
            column_name="close_ts",
            column_sql="TIMESTAMP WITH TIME ZONE",
        )
        self._ensure_table_column(
            table_name="audit_logs",
            column_name="run_id",
            column_sql="VARCHAR",
        )
        self._ensure_table_column(
            table_name="trades",
            column_name="run_id",
            column_sql="VARCHAR",
        )
        self._ensure_table_column(
            table_name="raw_ticks",
            column_name="client_tick_seq",
            column_sql="BIGINT",
        )
        self._ensure_table_column(
            table_name="raw_ticks",
            column_name="run_id",
            column_sql="VARCHAR",
        )

    def _ensure_table_column(self, *, table_name: str, column_name: str, column_sql: str) -> None:
        colset = self._get_table_columns(table_name)
        if str(column_name).lower() not in colset:
            self._con.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
            )

    def _get_table_columns(self, table_name: str) -> set[str]:
        cols = self._con.execute(
            """
            SELECT lower(column_name)
            FROM information_schema.columns
            WHERE lower(table_name) = ?
            """,
            [str(table_name).lower()],
        ).fetchall()
        return {str(r[0]).lower() for r in cols}

    def _migrate_tick_bars_table(self) -> None:
        """Upgrade persisted tick_bars tables from legacy *_price columns once."""
        legacy_to_canonical = {
            "open_price": "open_bid",
            "high_price": "high_bid",
            "low_price": "low_bid",
            "close_price": "close_bid",
        }
        columns = self._get_table_columns("tick_bars")
        for legacy_name, canonical_name in legacy_to_canonical.items():
            if canonical_name in columns:
                continue
            if legacy_name in columns:
                self._con.execute(
                    f"ALTER TABLE tick_bars RENAME COLUMN {legacy_name} TO {canonical_name}"
                )
                columns.remove(legacy_name)
                columns.add(canonical_name)

        self._ensure_table_column(
            table_name="tick_bars",
            column_name="high_ask",
            column_sql="DOUBLE",
        )
        self._ensure_table_column(
            table_name="tick_bars",
            column_name="close_ask",
            column_sql="DOUBLE",
        )

    def append_bar(self, bar: IncomingTickBar) -> None:
        """Append a validated tick bar to the state buffer."""
        sym = bar.symbol.upper()
        key = f"{sym}_{bar.bar_ticks}"
        idx = self._row_counters.get(key, 0)
        self._con.execute(
            _INSERT_SQL,
            [
                idx,
                sym,
                bar.bar_ticks,
                bar.timestamp,
                bar.close_ts,
                bar.open_bid,
                bar.high_bid,
                bar.low_bid,
                bar.close_bid,
                bar.spread,
                bar.tick_volume,
                bar.hl_first,
                bar.hl_pos_frac,
                bar.high_ask,
                bar.close_ask,
            ],
        )
        self._row_counters[key] = idx + 1

        if (idx + 1) % 100 == 0:
            self._prune(sym, bar.bar_ticks, idx + 1)

    def _prune(self, symbol: str, bar_ticks: int, current_idx: int) -> None:
        """Delete old rows to prevent unbounded growth."""
        self._con.execute(
            "DELETE FROM tick_bars WHERE symbol = ? AND bar_ticks = ? AND row_id < ?",
            [symbol, bar_ticks, current_idx - 600],
        )

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        """Return the number of bars currently stored for a symbol + horizon."""
        r = self._con.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        return int(r[0]) if r else 0

    def get_latest_bar(self, symbol: str, bar_ticks: int) -> dict | None:
        """Get the most recent completed bar for a symbol/bar_ticks pair."""
        return self._get_bar_row(symbol=symbol, bar_ticks=bar_ticks, bar_number=None)

    def _get_bar_row(
        self,
        *,
        symbol: str,
        bar_ticks: int,
        bar_number: int | None,
    ) -> dict | None:
        """Get a completed bar row by number, or latest when bar_number is None."""
        row_filter = ""
        params: list[Any] = [symbol.upper(), bar_ticks]
        if bar_number is not None:
            row_filter = "AND row_id = ?"
            params.append(int(bar_number))
        res = self._con.execute(
            "SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid, "
            "spread, hl_first, hl_pos_frac, high_ask, close_ask "
            "FROM tick_bars WHERE symbol = ? AND bar_ticks = ? "
            f"{row_filter} "
            "ORDER BY row_id DESC LIMIT 1",
            params,
        ).fetchone()
        if res is None:
            return None
        return {
            "row_id": res[0],
            "timestamp": res[1],
            "close_ts": res[2],
            "open_bid": res[3],
            "high_bid": res[4],
            "low_bid": res[5],
            "close_bid": res[6],
            "spread": res[7],
            "hl_first": res[8] if res[8] is not None else 0.0,
            "hl_pos_frac": res[9],
            "high_ask": res[10] if res[10] is not None else 0.0,
            "close_ask": res[11] if res[11] is not None else 0.0,
        }

    def get_latest_bar_context(self, symbol: str, bar_ticks: int) -> BarContext | None:
        """Build the public completed-bar context for runtime lifecycle consumers."""
        return self.get_bar_context(symbol, bar_ticks)

    def get_bar_context(
        self,
        symbol: str,
        bar_ticks: int,
        *,
        bar_number: int | None = None,
        side: str | None = None,
    ) -> BarContext | None:
        """Build the public completed-bar context for runtime lifecycle consumers."""
        latest = self._get_bar_row(symbol=symbol, bar_ticks=bar_ticks, bar_number=bar_number)
        if latest is None:
            return None
        normalized_side = None if side is None else str(side).strip().upper()
        return BarContext(
            symbol=symbol.upper(),
            bar_ticks=int(bar_ticks),
            bar_idx=int(latest["row_id"]),
            timestamp=latest["timestamp"],
            close_ts=latest["close_ts"],
            spread=float(latest["spread"]) if latest["spread"] is not None else None,
            side=normalized_side,
            bid=BarPrices(
                high=float(latest["high_bid"]),
                low=float(latest["low_bid"]),
                close=float(latest["close_bid"]),
            ),
            ask=BarPrices(
                high=float(latest["high_ask"]),
                low=float(min(latest["high_ask"], latest["close_ask"])),
                close=float(latest["close_ask"]),
            ),
            hl_first=float(latest.get("hl_first", 0.0) or 0.0),
            hl_pos_frac=(
                float(latest["hl_pos_frac"])
                if latest.get("hl_pos_frac") is not None
                else None
            ),
        )

    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        """Return the close_ts of the most recent bar."""
        r = self._con.execute(
            "SELECT close_ts FROM tick_bars WHERE symbol = ? ORDER BY row_id DESC LIMIT 1",
            [symbol.upper()],
        ).fetchone()
        return r[0] if r else None

    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        """Compute the 16-parameter feature vector for the latest bar.

        Delegates all rolling-window math to the canonical builder in
        ``src.behemoth.core.features.compute_features_from_bars()``.

        Returns None if the buffer has insufficient warmup history.
        """
        sym = symbol.upper()
        n = self.bar_count(sym, bar_ticks)
        if n < self._cfg.full_warmup_bars:
            return None

        df = self._con.execute(_SELECT_SQL, [sym, bar_ticks]).fetchdf()

        return compute_features_from_bars(
            df,
            symbol=sym,
            bar_ticks=bar_ticks,
            horizon=horizon,
            barrier_pips=barrier_pips,
            cfg=self._cfg,
        )

    def compute_regime_quantiles(self, symbol: str, bar_ticks: int) -> dict[str, float]:
        """Compute runtime regime quantiles from the recent bar buffer."""
        sym = symbol.upper()
        n = self.bar_count(sym, bar_ticks)
        if n < self._cfg.full_warmup_bars:
            return {}
        df = self._con.execute(_SELECT_SQL, [sym, bar_ticks]).fetchdf()
        return compute_regime_quantiles_from_bars(df, symbol=sym, cfg=self._cfg)

    def log_audit_event(
        self,
        symbol: str,
        candidate_uid: str,
        pred_prob: float,
        threshold: float,
        features: ModelFeatures,
        model_month: str,
        close_ts: datetime | None = None,
        run_id: str | None = None,
    ) -> None:
        """Record an execution decision snapshot into the persistent audit trail."""
        self._con.execute(
            _AUDIT_INSERT_SQL,
            [
                close_ts,
                symbol.upper(),
                candidate_uid,
                float(pred_prob),
                float(threshold),
                features.model_dump_json(),
                model_month,
                run_id,
            ],
        )

    def log_audit_event_batch(self, events: list[tuple]) -> None:
        """Record a batch of execution decisions into the persistent audit trail."""
        if not events:
            return
        self._con.executemany(_AUDIT_INSERT_SQL, events)

    def purge_audit_events(self, *, symbol: str, run_id: str) -> int:
        """Delete audit_logs rows matching (symbol, run_id). Returns rows deleted.

        Scoped purge only - does not affect other symbols or other run_ids
        (e.g. 'threshold_seed' or 'jforex_live' rows are untouched).
        """
        deleted_rows = self._con.execute(
            "DELETE FROM audit_logs WHERE symbol = ? AND run_id = ? RETURNING 1",
            [symbol.upper(), run_id],
        ).fetchall()
        return len(deleted_rows)

    def seed_training_predictions(
        self,
        *,
        parquet_path: Path,
        symbol: str,
        candidate_uid: str,
        model_month: str,
        run_id: str,
    ) -> int:
        """Seed audit_logs with exported training predictions (phase 1).

        Loads the training predictions parquet and inserts rows into audit_logs
        with close_ts set to midnight UTC of each day. This gives the rolling
        threshold the same starting pool that WFO had on test day 1.

        Returns the number of rows inserted.
        """
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        if df.empty:
            return 0
        events = []
        for row in df.itertuples(index=False):
            day_ts = datetime(row.day.year, row.day.month, row.day.day, tzinfo=timezone.utc)
            events.append((
                day_ts,           # close_ts
                symbol.upper(),   # symbol
                candidate_uid,    # candidate_uid
                float(row.pred_prob),  # pred_prob
                0.0,              # threshold (not meaningful for seed)
                "{}",             # features_json
                model_month,      # model_month
                run_id,           # run_id
            ))
        self.log_audit_event_batch(events)
        return len(events)

    def log_predict_evaluation(
        self,
        *,
        close_ts: datetime | None,
        symbol: str,
        candidate_uid: str,
        pred_prob: float,
        threshold: float,
        preselected_exec: int,
        selected_exec: int,
        threshold_blocked: bool,
        threshold_block_reason: str | None,
        risk_blocked: bool,
        risk_block_reason: str | None,
        model_month: str,
        run_id: str | None,
    ) -> None:
        """Record a prediction evaluation snapshot regardless of gate outcome."""
        self._con.execute(
            _PREDICT_EVAL_INSERT_SQL,
            [
                close_ts,
                symbol.upper(),
                candidate_uid,
                float(pred_prob),
                float(threshold),
                int(preselected_exec),
                int(selected_exec),
                bool(threshold_blocked),
                threshold_block_reason,
                bool(risk_blocked),
                risk_block_reason,
                model_month,
                run_id,
            ],
        )

    def open_trade(
        self,
        symbol: str,
        candidate_uid: str,
        broker_pos_id: str,
        side: str,
        entry_price: float,
        entry_ts: datetime,
        horizon: int,
        reservation_id: str | None = None,
        run_id: str | None = None,
    ) -> str:
        """Record the opening of a position."""
        import uuid
        internal_id = str(uuid.uuid4())

        res = self._con.execute(
            "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [symbol.upper()]
        ).fetchone()
        entry_bar_id = res[0] if res and res[0] is not None else 0

        audit_res = self._con.execute(
            "SELECT pred_prob, threshold, model_month FROM audit_logs "
            "WHERE candidate_uid = ? AND symbol = ? ORDER BY event_ts DESC LIMIT 1",
            [candidate_uid, symbol.upper()],
        ).fetchone()
        if audit_res:
            entry_pred_prob, entry_threshold, entry_model_month = audit_res
        else:
            import logging
            logging.getLogger(__name__).warning(
                "open_trade: no audit_logs row for candidate_uid=%s symbol=%s; model context NULL",
                candidate_uid, symbol,
            )
            entry_pred_prob, entry_threshold, entry_model_month = None, None, None

        self._con.execute(
            """INSERT INTO trades (
                internal_trade_id, broker_pos_id, symbol, candidate_uid, side,
                entry_price, entry_ts, entry_bar_id, horizon_bars, status, run_id,
                reservation_id, entry_pred_prob, entry_threshold, entry_model_month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)""",
            [internal_id, broker_pos_id, symbol.upper(), candidate_uid, side,
             float(entry_price), entry_ts, entry_bar_id, horizon, run_id,
             reservation_id, entry_pred_prob, entry_threshold, entry_model_month],
        )
        return internal_id

    def get_active_trades(self, symbol: str) -> list[dict]:
        """Fetch all currently OPEN trades for state recovery."""
        res = self._con.execute(
            "SELECT broker_pos_id, entry_bar_id, horizon_bars, touch_bar_id FROM trades WHERE symbol = ? AND status = 'OPEN'",
            [symbol.upper()],
        ).fetchall()
        return [
            {"broker_pos_id": r[0], "entry_bar_id": r[1], "horizon": r[2], "touch_bar_id": r[3]}
            for r in res
        ]

    def get_last_bar_close_price(
        self, symbol: str, bar_ticks: int = 100
    ) -> tuple[float, datetime] | None:
        """Return (close_bid, close_ts) for the most recent bar, or None if no data."""
        res = self._con.execute(
            "SELECT close_bid, close_ts FROM tick_bars "
            "WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id DESC LIMIT 1",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        if res is None:
            return None
        close_bid, close_ts = res
        close_ts = (
            close_ts.replace(tzinfo=timezone.utc)
            if close_ts.tzinfo is None
            else close_ts.astimezone(timezone.utc)
        )
        return float(close_bid), close_ts

    def touch_trade(self, broker_pos_id: str, touch_bar_id: int) -> None:
        """Record the bar id when a position's barrier was touched."""
        self._con.execute(
            "UPDATE trades SET touch_bar_id = ? WHERE broker_pos_id = ?",
            [touch_bar_id, broker_pos_id],
        )

    def update_trade(
        self,
        broker_pos_id: str,
        status: str,
        exit_price: float | None = None,
        exit_ts: datetime | None = None,
        pnl_pips: float | None = None,
        run_id: str | None = None,
        symbol: str | None = None,
        close_reason: str | None = None,
        commission_ccy: float | None = None,
    ) -> None:
        """Update a trade status and exit data (CLOSED/CANCELLED)."""
        exit_bar_id = None
        if symbol:
            res = self._con.execute(
                "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [symbol.upper()]
            ).fetchone()
            exit_bar_id = res[0] if res and res[0] is not None else None

        if run_id:
            self._con.execute(
                "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ?, "
                "run_id = COALESCE(run_id, ?), exit_bar_id = ?, close_reason = ?, commission_ccy = ? "
                "WHERE broker_pos_id = ?",
                [status, exit_price, exit_ts, pnl_pips, run_id,
                 exit_bar_id, close_reason, commission_ccy, broker_pos_id],
            )
            return
        self._con.execute(
            "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ?, "
            "exit_bar_id = ?, close_reason = ?, commission_ccy = ? "
            "WHERE broker_pos_id = ?",
            [status, exit_price, exit_ts, pnl_pips,
             exit_bar_id, close_reason, commission_ccy, broker_pos_id],
        )

    def get_ledger_stats(self) -> list[dict]:
        """Aggregate trade statistics for Prometheus gauges."""
        res = self._con.execute("""
            SELECT
                symbol,
                SUM(CASE WHEN status = 'CLOSED' THEN pnl_pips ELSE 0 END) as total_pnl,
                COUNT(CASE WHEN status = 'CLOSED' AND pnl_pips > 0 THEN 1 END) as wins,
                COUNT(CASE WHEN status = 'CLOSED' THEN 1 END) as closed_trades
            FROM trades
            GROUP BY symbol
        """).fetchall()
        return [
            {
                "symbol": r[0],
                "total_pnl": r[1] or 0.0,
                "win_rate": (r[2] / r[3]) if r[3] > 0 else 0.0,
                "closed_trades": r[3]
            }
            for r in res
        ]

    def get_rolling_threshold(
        self,
        symbol: str,
        candidate_uid: str,
        exec_q: float,
        lookback_days: int,
        min_history: int,
    ) -> float | None:
        """Compute rolling execution threshold from recent audit_logs pred_probs.

        Returns the exec_q quantile of pred_probs over the last lookback_days
        calendar days. Returns None if fewer than min_history events exist in
        that window (insufficient history to compute a reliable threshold).
        """
        from datetime import timedelta
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
        row = self._con.execute(
            """
            SELECT COUNT(*), quantile(pred_prob, ?)
            FROM audit_logs
            WHERE symbol = ?
              AND candidate_uid = ?
              AND close_ts >= ?
            """,
            [float(exec_q), symbol.upper(), candidate_uid, cutoff],
        ).fetchone()
        if row is None or row[0] is None or int(row[0]) < min_history:
            return None
        return float(row[1])

    def get_all_symbols(self) -> list[str]:
        """Return all unique symbols in the tick_bars table."""
        res = self._con.execute("SELECT DISTINCT symbol FROM tick_bars").fetchall()
        return [r[0] for r in res]

    def record_account_risk_snapshot(
        self,
        *,
        symbol: str,
        balance: float,
        equity: float,
        snapshot_ts: datetime,
    ) -> None:
        """Persist an account-level account risk snapshot emitted by cBot."""
        ts = snapshot_ts
        ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
        self._con.execute(
            _ACCOUNT_RISK_SNAPSHOT_INSERT_SQL,
            [ts, symbol.upper(), float(balance), float(equity)],
        )

    def record_account_snapshot(
        self,
        *,
        symbol: str,
        balance: float,
        equity: float,
        snapshot_ts: datetime,
    ) -> None:
        """Broker-neutral alias for account snapshot persistence."""
        self.record_account_risk_snapshot(
            symbol=symbol,
            balance=balance,
            equity=equity,
            snapshot_ts=snapshot_ts,
        )

    def get_latest_account_risk_snapshot(self, symbol: str | None = None) -> dict | None:
        """Return the latest account snapshot, optionally filtered by symbol."""
        if symbol:
            row = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM account_risk_snapshots
                WHERE symbol = ?
                ORDER BY snapshot_ts DESC
                LIMIT 1
                """,
                [symbol.upper()],
            ).fetchone()
        else:
            row = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM account_risk_snapshots
                ORDER BY snapshot_ts DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        ts = row[0]
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        return {
            "snapshot_ts": ts,
            "symbol": row[1],
            "balance": float(row[2]),
            "equity": float(row[3]),
        }

    def get_latest_account_snapshot(self, symbol: str | None = None) -> dict | None:
        """Broker-neutral alias for latest account snapshot retrieval."""
        return self.get_latest_account_risk_snapshot(symbol)

    def get_account_risk_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        """Return ordered account risk snapshots since a UTC timestamp."""
        s = since_ts
        s = s.replace(tzinfo=timezone.utc) if s.tzinfo is None else s.astimezone(timezone.utc)
        if symbol:
            rows = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM account_risk_snapshots
                WHERE snapshot_ts >= ? AND symbol = ?
                ORDER BY snapshot_ts ASC
                """,
                [s, symbol.upper()],
            ).fetchall()
        else:
            rows = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM account_risk_snapshots
                WHERE snapshot_ts >= ?
                ORDER BY snapshot_ts ASC
                """,
                [s],
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            ts = r[0]
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
            out.append(
                {
                    "snapshot_ts": ts,
                    "symbol": r[1],
                    "balance": float(r[2]),
                    "equity": float(r[3]),
                }
            )
        return out

    def get_account_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        """Broker-neutral alias for historical account snapshots."""
        return self.get_account_risk_snapshots_since(since_ts=since_ts, symbol=symbol)

    def create_account_risk_reservation(
        self,
        *,
        symbol: str,
        candidate_uid: str,
        reserved_loss_ccy: float,
        barrier_pips: float,
        cap_pips: float,
        cost_est_pips: float,
        volume_units: float,
        side: str | None = None,
        source: str = "predict_allocator",
        status: str = "PENDING",
    ) -> str:
        """Create an account risk reservation row and return reservation id."""
        import uuid

        initial_state = ReservationStateMachine.validate_initial(status)
        rid = str(uuid.uuid4())
        now_utc = datetime.now(tz=timezone.utc)
        self._con.execute(
            _ACCOUNT_RISK_RES_INSERT_SQL,
            [
                rid,
                now_utc,
                now_utc,
                symbol.upper(),
                candidate_uid,
                None,
                initial_state.value,
                float(reserved_loss_ccy),
                float(barrier_pips),
                float(cap_pips),
                float(cost_est_pips),
                float(volume_units),
                side,
                source,
            ],
        )
        return rid

    def transition_account_risk_reservation(
        self,
        reservation_id: str,
        target_status: str | ReservationState,
        *,
        broker_pos_id: str | None = None,
        reason: str | None = None,
    ) -> str:
        """Transition one reservation through the formal lifecycle."""
        row = self._con.execute(
            """
            SELECT status
            FROM account_risk_reservations
            WHERE reservation_id = ?
            LIMIT 1
            """,
            [reservation_id],
        ).fetchone()
        if row is None:
            raise KeyError(f"reservation not found: {reservation_id}")
        target = ReservationStateMachine.validate_transition(str(row[0]), target_status)
        now_utc = datetime.now(tz=timezone.utc)
        safe_reason = str(reason or "").replace("|", "_").replace("'", "_")
        if safe_reason:
            self._con.execute(
                """
                UPDATE account_risk_reservations
                SET status = ?, broker_pos_id = COALESCE(?, broker_pos_id),
                    updated_ts = ?, source = source || ?
                WHERE reservation_id = ?
                """,
                [target.value, broker_pos_id, now_utc, f"|{safe_reason}", reservation_id],
            )
        else:
            self._con.execute(
                """
                UPDATE account_risk_reservations
                SET status = ?, broker_pos_id = COALESCE(?, broker_pos_id), updated_ts = ?
                WHERE reservation_id = ?
                """,
                [target.value, broker_pos_id, now_utc, reservation_id],
            )
        return target.value

    def create_risk_reservation(
        self,
        *,
        symbol: str,
        candidate_uid: str,
        reserved_loss_ccy: float,
        barrier_pips: float,
        cap_pips: float,
        cost_est_pips: float,
        volume_units: float,
        side: str | None = None,
        source: str = "predict_allocator",
        status: str = "PENDING",
    ) -> str:
        """Broker-neutral alias for creating risk reservations."""
        return self.create_account_risk_reservation(
            symbol=symbol,
            candidate_uid=candidate_uid,
            reserved_loss_ccy=reserved_loss_ccy,
            barrier_pips=barrier_pips,
            cap_pips=cap_pips,
            cost_est_pips=cost_est_pips,
            volume_units=volume_units,
            side=side,
            source=source,
            status=status,
        )

    def promote_account_risk_reservation(
        self,
        *,
        broker_pos_id: str,
        reservation_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
    ) -> str | None:
        """Promote a pending reservation to OPEN after broker fill."""
        if reservation_id:
            row = self._con.execute(
                """
                SELECT reservation_id
                FROM account_risk_reservations
                WHERE reservation_id = ? AND status = 'PENDING'
                LIMIT 1
                """,
                [reservation_id],
            ).fetchone()
            if not row:
                return None
            self.transition_account_risk_reservation(
                str(reservation_id),
                ReservationState.OPEN,
                broker_pos_id=broker_pos_id,
            )
            return str(reservation_id)

        if not candidate_uid:
            return None

        params: list = [candidate_uid]
        query = """
            SELECT reservation_id
            FROM account_risk_reservations
            WHERE candidate_uid = ? AND status = 'PENDING'
        """
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_ts ASC LIMIT 1"
        row = self._con.execute(query, params).fetchone()
        if not row:
            return None
        rid = str(row[0])
        self.transition_account_risk_reservation(
            rid,
            ReservationState.OPEN,
            broker_pos_id=broker_pos_id,
        )
        return rid

    def promote_risk_reservation(
        self,
        *,
        broker_pos_id: str,
        reservation_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
    ) -> str | None:
        """Broker-neutral alias for opening reservations after broker fill."""
        return self.promote_account_risk_reservation(
            broker_pos_id=broker_pos_id,
            reservation_id=reservation_id,
            candidate_uid=candidate_uid,
            symbol=symbol,
        )

    def release_account_risk_reservation(
        self,
        *,
        reservation_id: str | None = None,
        broker_pos_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
        reason: str = "released",
    ) -> int:
        """Release active reservation rows and return affected row count."""
        params: list = []
        where = ["status IN ('PENDING', 'OPEN')"]
        if reservation_id:
            where.append("reservation_id = ?")
            params.append(reservation_id)
        if broker_pos_id:
            where.append("broker_pos_id = ?")
            params.append(broker_pos_id)
        if candidate_uid:
            where.append("candidate_uid = ?")
            params.append(candidate_uid)
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.upper())
        if len(where) == 1:
            return 0
        where_sql = " AND ".join(where)
        rows = self._con.execute(
            f"SELECT reservation_id FROM account_risk_reservations WHERE {where_sql}",
            params,
        ).fetchall()
        if not rows:
            return 0
        for row in rows:
            self.transition_account_risk_reservation(
                str(row[0]),
                ReservationState.RELEASED,
                reason=reason,
            )
        return len(rows)

    def release_risk_reservation(
        self,
        *,
        reservation_id: str | None = None,
        broker_pos_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
        reason: str = "released",
    ) -> int:
        """Broker-neutral alias for releasing active reservations."""
        return self.release_account_risk_reservation(
            reservation_id=reservation_id,
            broker_pos_id=broker_pos_id,
            candidate_uid=candidate_uid,
            symbol=symbol,
            reason=reason,
        )

    def expire_stale_account_risk_pending_reservations(self, *, max_age_seconds: int) -> int:
        """Expire pending reservations older than max_age_seconds."""
        now_utc = datetime.now(tz=timezone.utc)
        cutoff = now_utc.timestamp() - float(max_age_seconds)
        cutoff_ts = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        rows = self._con.execute(
            """
            SELECT reservation_id
            FROM account_risk_reservations
            WHERE status = 'PENDING' AND created_ts < ?
            """,
            [cutoff_ts],
        ).fetchall()
        if not rows:
            return 0
        for row in rows:
            self.transition_account_risk_reservation(
                str(row[0]),
                ReservationState.EXPIRED,
                reason="stale_pending",
            )
        return len(rows)

    def expire_stale_pending_reservations(self, *, max_age_seconds: int) -> int:
        """Broker-neutral alias for expiring stale pending reservations."""
        return self.expire_stale_account_risk_pending_reservations(max_age_seconds=max_age_seconds)

    def sum_active_account_risk_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        """Return total active reserved account risk loss in account currency."""
        statuses: list[str] = []
        if include_pending:
            statuses.append("PENDING")
        if include_open:
            statuses.append("OPEN")
        if not statuses:
            return 0.0
        placeholders = ",".join(["?"] * len(statuses))
        params: list[Any] = list(statuses)
        query = f"""
            SELECT COALESCE(SUM(reserved_loss_ccy), 0.0)
            FROM account_risk_reservations
            WHERE status IN ({placeholders})
        """
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        row = self._con.execute(query, params).fetchone()
        if not row or row[0] is None:
            return 0.0
        return float(row[0])

    def sum_active_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        """Broker-neutral alias for active reserved loss totals."""
        return self.sum_active_account_risk_reserved_loss_ccy(
            symbol=symbol,
            include_pending=include_pending,
            include_open=include_open,
        )

    def list_active_account_risk_reservations(self, *, symbol: str | None = None) -> list[dict]:
        """Return active PENDING/OPEN account risk reservations."""
        params: list[Any] = []
        query = """
            SELECT reservation_id, created_ts, updated_ts, symbol, candidate_uid, broker_pos_id,
                   status, reserved_loss_ccy, barrier_pips, cap_pips, cost_est_pips, volume_units,
                   side, source
            FROM account_risk_reservations
            WHERE status IN ('PENDING', 'OPEN')
        """
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_ts ASC"
        rows = self._con.execute(query, params).fetchall()
        out: list[dict] = []
        for r in rows:
            created_ts = r[1]
            if isinstance(created_ts, datetime):
                created_ts = created_ts.replace(tzinfo=timezone.utc) if created_ts.tzinfo is None else created_ts.astimezone(timezone.utc)
            updated_ts = r[2]
            if isinstance(updated_ts, datetime):
                updated_ts = updated_ts.replace(tzinfo=timezone.utc) if updated_ts.tzinfo is None else updated_ts.astimezone(timezone.utc)
            out.append(
                {
                    "reservation_id": str(r[0]),
                    "created_ts": created_ts,
                    "updated_ts": updated_ts,
                    "symbol": str(r[3]),
                    "candidate_uid": str(r[4]),
                    "broker_pos_id": r[5],
                    "status": str(r[6]),
                    "reserved_loss_ccy": float(r[7]),
                    "barrier_pips": float(r[8]),
                    "cap_pips": float(r[9]),
                    "cost_est_pips": float(r[10]),
                    "volume_units": float(r[11]),
                    "side": r[12],
                    "source": r[13],
                }
            )
        return out

    def list_active_risk_reservations(self, *, symbol: str | None = None) -> list[dict]:
        """Broker-neutral alias for active risk reservation rows."""
        return self.list_active_account_risk_reservations(symbol=symbol)

    def log_account_risk_allocator_event(
        self,
        *,
        symbol: str,
        candidate_uid: str,
        status: str,
        block_reason: str | None,
        reserved_loss_ccy: float | None,
        requested_volume_units: float,
        pred_prob: float,
        threshold_exec: float,
        risk_rank_score: float | None,
        reservation_id: str | None,
    ) -> None:
        """Persist allocator decision events for monitoring and reconciliation."""
        now_utc = datetime.now(tz=timezone.utc)
        self._con.execute(
            _ACCOUNT_RISK_ALLOC_EVENT_INSERT_SQL,
            [
                now_utc,
                symbol.upper(),
                candidate_uid,
                str(status).upper(),
                block_reason,
                float(reserved_loss_ccy) if reserved_loss_ccy is not None else None,
                float(requested_volume_units),
                float(pred_prob),
                float(threshold_exec),
                float(risk_rank_score) if risk_rank_score is not None else None,
                reservation_id,
            ],
        )

    def log_allocator_event(
        self,
        *,
        symbol: str,
        candidate_uid: str,
        status: str,
        block_reason: str | None,
        reserved_loss_ccy: float | None,
        requested_volume_units: float,
        pred_prob: float,
        threshold_exec: float,
        risk_rank_score: float | None,
        reservation_id: str | None,
    ) -> None:
        """Broker-neutral alias for allocator monitoring events."""
        self.log_account_risk_allocator_event(
            symbol=symbol,
            candidate_uid=candidate_uid,
            status=status,
            block_reason=block_reason,
            reserved_loss_ccy=reserved_loss_ccy,
            requested_volume_units=requested_volume_units,
            pred_prob=pred_prob,
            threshold_exec=threshold_exec,
            risk_rank_score=risk_rank_score,
            reservation_id=reservation_id,
        )

    def record_raw_tick(self, tick: IncomingTick, *, source: str = "live") -> None:
        """Persist a single raw tick for replay/reconciliation workflows."""
        ts = tick.timestamp
        ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
        self._con.execute(
            _RAW_TICK_INSERT_SQL,
            [
                ts,
                datetime.now(tz=timezone.utc),
                tick.symbol.upper(),
                float(tick.bid),
                float(tick.ask),
                float(tick.ask - tick.bid),
                float(tick.tick_volume),
                str(source),
                (int(tick.client_tick_seq) if tick.client_tick_seq is not None else None),
                (str(tick.run_id).strip() if str(tick.run_id or "").strip() else None),
            ],
        )

    def raw_tick_count(self, symbol: str | None = None) -> int:
        """Return stored raw tick rows, optionally filtered by symbol."""
        if symbol:
            row = self._con.execute(
                "SELECT COUNT(*) FROM raw_ticks WHERE symbol = ?",
                [symbol.upper()],
            ).fetchone()
        else:
            row = self._con.execute("SELECT COUNT(*) FROM raw_ticks").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def get_open_trade_entry_price(self, reservation_id: str) -> float | None:
        """Return entry_price of the OPEN trade for the given reservation, or None."""
        row = self._con.execute(
            "SELECT entry_price FROM trades WHERE reservation_id = ? AND status = 'OPEN'",
            [reservation_id],
        ).fetchone()
        return float(row[0]) if row else None

    def get_latest_bar_id(self, symbol: str) -> int:
        """Return MAX(row_id) for tick_bars of this symbol, or 0 if no rows exist."""
        row = self._con.execute(
            "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?",
            [symbol.upper()],
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def get_latest_tick_snapshot(self, symbol: str) -> tuple[float, datetime] | None:
        """Return (close_bid, close_ts) for the most recent bar across all bar_ticks, or None."""
        row = self._con.execute(
            "SELECT close_bid, close_ts FROM tick_bars WHERE symbol = ? ORDER BY close_ts DESC, row_id DESC LIMIT 1",
            [symbol.upper()],
        ).fetchone()
        if not row or row[0] is None:
            return None
        close_ts = row[1]
        if isinstance(close_ts, datetime):
            close_ts = (
                close_ts.replace(tzinfo=timezone.utc)
                if close_ts.tzinfo is None
                else close_ts.astimezone(timezone.utc)
            )
        return float(row[0]), close_ts

    def count_audit_logs(self, symbol: str, run_id: str) -> int:
        """Return count of audit_logs rows matching (symbol, run_id)."""
        row = self._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
            [symbol.upper(), run_id],
        ).fetchone()
        return int(row[0]) if row else 0

    def clear_audit_logs_by_run_id(self, run_id: str) -> None:
        """Delete all audit_logs rows matching run_id (all symbols)."""
        self._con.execute("DELETE FROM audit_logs WHERE run_id = ?", [run_id])

    def atomic_audit_replace(
        self, symbol: str, run_id: str, events_batch: list[tuple]
    ) -> int:
        """Delete existing audit rows for (symbol, run_id) and insert events_batch atomically."""
        from contextlib import suppress

        self._con.execute("BEGIN TRANSACTION")
        try:
            purged = self.purge_audit_events(symbol=symbol, run_id=run_id)
            self.log_audit_event_batch(events_batch)
            self._con.execute("COMMIT")
            return purged
        except Exception:
            with suppress(Exception):
                self._con.execute("ROLLBACK")
            raise

    def export_warmup_bars(self, symbol: str, bar_ticks: int, path: Path) -> int:
        """Export tick_bars rows for (symbol, bar_ticks) to a parquet file. Returns row count."""
        row = self._con.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
            [symbol.upper(), bar_ticks],
        ).fetchone()
        count = int(row[0]) if row else 0
        if count == 0:
            return 0
        self._con.execute(
            f"""
            COPY (
                SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid,
                       spread, tick_volume, hl_first, hl_pos_frac, high_ask, close_ask
                FROM tick_bars
                WHERE symbol = ? AND bar_ticks = ?
                ORDER BY row_id
            ) TO '{path}' (FORMAT PARQUET)
            """,
            [symbol.upper(), bar_ticks],
        )
        return count

    def checkpoint(self) -> None:
        """Run a DuckDB CHECKPOINT to flush WAL to disk."""
        self._con.execute("CHECKPOINT")

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()
