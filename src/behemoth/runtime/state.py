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
from typing import Any

import duckdb

from src.behemoth.core.features import (
    FeatureConfig,
    compute_features_from_bars,
    compute_regime_quantiles_from_bars,
)
from src.behemoth.core.schemas import IncomingTick, IncomingTickBar, ModelFeatures

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tick_bars (
    row_id INTEGER,
    symbol VARCHAR,
    bar_ticks INTEGER,
    ts TIMESTAMP WITH TIME ZONE,
    close_ts TIMESTAMP WITH TIME ZONE,
    open_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    close_price DOUBLE,
    spread DOUBLE,
    tick_volume DOUBLE,
    hl_first DOUBLE,
    hl_pos_frac DOUBLE
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
    run_id VARCHAR
);

CREATE TABLE IF NOT EXISTS ftmo_account_snapshots (
    snapshot_ts TIMESTAMP WITH TIME ZONE,
    symbol VARCHAR,
    balance DOUBLE,
    equity DOUBLE
);

CREATE TABLE IF NOT EXISTS ftmo_risk_reservations (
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

CREATE TABLE IF NOT EXISTS ftmo_allocator_events (
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
    "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_SQL = """
SELECT * FROM (
    SELECT row_id, ts, close_ts, open_price, high_price, low_price,
           close_price, spread, tick_volume, hl_first, hl_pos_frac
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

_FTMO_SNAPSHOT_INSERT_SQL = (
    "INSERT INTO ftmo_account_snapshots VALUES (?, ?, ?, ?)"
)

_FTMO_RISK_RES_INSERT_SQL = (
    "INSERT INTO ftmo_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_FTMO_ALLOC_EVENT_INSERT_SQL = (
    "INSERT INTO ftmo_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
        """Add new debug columns for backward-compatible schema migration."""
        try:
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
        except Exception:
            # Best-effort migration only; avoid startup hard failure.
            pass

    def _ensure_table_column(self, *, table_name: str, column_name: str, column_sql: str) -> None:
        cols = self._con.execute(
            """
            SELECT lower(column_name)
            FROM information_schema.columns
            WHERE lower(table_name) = ?
            """,
            [str(table_name).lower()],
        ).fetchall()
        colset = {str(r[0]).lower() for r in cols}
        if str(column_name).lower() not in colset:
            self._con.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
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
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.spread,
                bar.tick_volume,
                bar.hl_first,
                bar.hl_pos_frac,
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

    def open_trade(
        self,
        symbol: str,
        candidate_uid: str,
        broker_pos_id: str,
        side: str,
        entry_price: float,
        entry_ts: datetime,
        horizon: int,
        run_id: str | None = None,
    ) -> str:
        """Record the opening of a position from the cBot."""
        import uuid
        internal_id = str(uuid.uuid4())

        # Fetch current bar count for the symbol to anchor the horizon
        res = self._con.execute(
            "SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [symbol.upper()]
        ).fetchone()
        entry_bar_id = res[0] if res and res[0] is not None else 0

        self._con.execute(
            "INSERT INTO trades (internal_trade_id, broker_pos_id, symbol, candidate_uid, side, entry_price, entry_ts, entry_bar_id, horizon_bars, status, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)",
            [internal_id, broker_pos_id, symbol.upper(), candidate_uid, side, float(entry_price), entry_ts, entry_bar_id, horizon, run_id],
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
    ) -> None:
        """Update a trade status and exit data (CLOSED/CANCELLED)."""
        if run_id:
            self._con.execute(
                "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ?, run_id = COALESCE(run_id, ?) WHERE broker_pos_id = ?",
                [status, exit_price, exit_ts, pnl_pips, run_id, broker_pos_id],
            )
            return
        self._con.execute(
            "UPDATE trades SET status = ?, exit_price = ?, exit_ts = ?, pnl_pips = ? WHERE broker_pos_id = ?",
            [status, exit_price, exit_ts, pnl_pips, broker_pos_id],
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

    def get_all_symbols(self) -> list[str]:
        """Return all unique symbols in the tick_bars table."""
        res = self._con.execute("SELECT DISTINCT symbol FROM tick_bars").fetchall()
        return [r[0] for r in res]

    def record_ftmo_account_snapshot(
        self,
        *,
        symbol: str,
        balance: float,
        equity: float,
        snapshot_ts: datetime,
    ) -> None:
        """Persist an account-level FTMO snapshot emitted by cBot."""
        ts = snapshot_ts
        ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
        self._con.execute(
            _FTMO_SNAPSHOT_INSERT_SQL,
            [ts, symbol.upper(), float(balance), float(equity)],
        )

    def get_latest_ftmo_account_snapshot(self, symbol: str | None = None) -> dict | None:
        """Return the latest account snapshot, optionally filtered by symbol."""
        if symbol:
            row = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM ftmo_account_snapshots
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
                FROM ftmo_account_snapshots
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

    def get_ftmo_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        """Return ordered FTMO snapshots since a UTC timestamp."""
        s = since_ts
        s = s.replace(tzinfo=timezone.utc) if s.tzinfo is None else s.astimezone(timezone.utc)
        if symbol:
            rows = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM ftmo_account_snapshots
                WHERE snapshot_ts >= ? AND symbol = ?
                ORDER BY snapshot_ts ASC
                """,
                [s, symbol.upper()],
            ).fetchall()
        else:
            rows = self._con.execute(
                """
                SELECT snapshot_ts, symbol, balance, equity
                FROM ftmo_account_snapshots
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

    def create_ftmo_risk_reservation(
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
        """Create a FTMO risk reservation row and return reservation id."""
        import uuid

        rid = str(uuid.uuid4())
        now_utc = datetime.now(tz=timezone.utc)
        self._con.execute(
            _FTMO_RISK_RES_INSERT_SQL,
            [
                rid,
                now_utc,
                now_utc,
                symbol.upper(),
                candidate_uid,
                None,
                status.upper(),
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

    def promote_ftmo_risk_reservation(
        self,
        *,
        broker_pos_id: str,
        reservation_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
    ) -> str | None:
        """Promote a pending reservation to OPEN after broker fill."""
        now_utc = datetime.now(tz=timezone.utc)
        if reservation_id:
            row = self._con.execute(
                """
                SELECT reservation_id
                FROM ftmo_risk_reservations
                WHERE reservation_id = ? AND status = 'PENDING'
                LIMIT 1
                """,
                [reservation_id],
            ).fetchone()
            if not row:
                return None
            self._con.execute(
                """
                UPDATE ftmo_risk_reservations
                SET status = 'OPEN', broker_pos_id = ?, updated_ts = ?
                WHERE reservation_id = ?
                """,
                [broker_pos_id, now_utc, reservation_id],
            )
            return str(reservation_id)

        if not candidate_uid:
            return None

        params: list = [candidate_uid]
        query = """
            SELECT reservation_id
            FROM ftmo_risk_reservations
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
        self._con.execute(
            """
            UPDATE ftmo_risk_reservations
            SET status = 'OPEN', broker_pos_id = ?, updated_ts = ?
            WHERE reservation_id = ?
            """,
            [broker_pos_id, now_utc, rid],
        )
        return rid

    def release_ftmo_risk_reservation(
        self,
        *,
        reservation_id: str | None = None,
        broker_pos_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
        reason: str = "released",
    ) -> int:
        """Release active reservation rows and return affected row count."""
        now_utc = datetime.now(tz=timezone.utc)
        safe_reason = str(reason).replace("|", "_").replace("'", "_")
        params: list = [now_utc]
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
        before = self._con.execute(
            f"SELECT COUNT(*) FROM ftmo_risk_reservations WHERE {where_sql}",
            params[1:],
        ).fetchone()
        before_count = int(before[0]) if before and before[0] is not None else 0
        if before_count <= 0:
            return 0
        self._con.execute(
            f"""
            UPDATE ftmo_risk_reservations
            SET status = 'RELEASED', updated_ts = ?, source = source || '|{safe_reason}'
            WHERE {where_sql}
            """,
            params,
        )
        return before_count

    def expire_stale_ftmo_pending_reservations(self, *, max_age_seconds: int) -> int:
        """Expire pending reservations older than max_age_seconds."""
        now_utc = datetime.now(tz=timezone.utc)
        cutoff = now_utc.timestamp() - float(max_age_seconds)
        cutoff_ts = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        before = self._con.execute(
            """
            SELECT COUNT(*)
            FROM ftmo_risk_reservations
            WHERE status = 'PENDING' AND created_ts < ?
            """,
            [cutoff_ts],
        ).fetchone()
        before_count = int(before[0]) if before and before[0] is not None else 0
        if before_count <= 0:
            return 0
        self._con.execute(
            """
            UPDATE ftmo_risk_reservations
            SET status = 'EXPIRED', updated_ts = ?
            WHERE status = 'PENDING'
              AND created_ts < ?
            """,
            [now_utc, cutoff_ts],
        )
        return before_count

    def sum_active_ftmo_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        """Return total active reserved FTMO loss in account currency."""
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
            FROM ftmo_risk_reservations
            WHERE status IN ({placeholders})
        """
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        row = self._con.execute(query, params).fetchone()
        if not row or row[0] is None:
            return 0.0
        return float(row[0])

    def list_active_ftmo_risk_reservations(self, *, symbol: str | None = None) -> list[dict]:
        """Return active PENDING/OPEN FTMO reservations."""
        params: list[Any] = []
        query = """
            SELECT reservation_id, created_ts, updated_ts, symbol, candidate_uid, broker_pos_id,
                   status, reserved_loss_ccy, barrier_pips, cap_pips, cost_est_pips, volume_units,
                   side, source
            FROM ftmo_risk_reservations
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

    def log_ftmo_allocator_event(
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
            _FTMO_ALLOC_EVENT_INSERT_SQL,
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

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()
