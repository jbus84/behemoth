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

from __future__ import annotations

from typing import Optional

import duckdb

from src.behemoth.core.features import FeatureConfig, compute_features_from_bars
from src.behemoth.core.schemas import IncomingTickBar, ModelFeatures

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
    symbol VARCHAR,
    candidate_uid VARCHAR,
    pred_prob DOUBLE,
    threshold DOUBLE,
    features_json VARCHAR,
    model_month VARCHAR
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
    status VARCHAR
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

_AUDIT_INSERT_SQL = (
    "INSERT INTO audit_logs VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)"
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
        self._row_counters: dict[str, int] = {}
        
        # Hydrate counters from persistent store to survive restarts
        res = self._con.execute(
            "SELECT symbol, bar_ticks, MAX(row_id) FROM tick_bars GROUP BY symbol, bar_ticks"
        ).fetchall()
        for r in res:
            if r[2] is not None:
                self._row_counters[f"{r[0].upper()}_{r[1]}"] = int(r[2]) + 1

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

    def get_latest_close_ts(self, symbol: str) -> Optional[datetime]:
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
    ) -> Optional[ModelFeatures]:
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

    def log_audit_event(
        self,
        symbol: str,
        candidate_uid: str,
        pred_prob: float,
        threshold: float,
        features: ModelFeatures,
        model_month: str,
    ) -> None:
        """Record an execution decision snapshot into the persistent audit trail."""
        self._con.execute(
            _AUDIT_INSERT_SQL,
            [
                symbol.upper(),
                candidate_uid,
                float(pred_prob),
                float(threshold),
                features.model_dump_json(),
                model_month,
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
            "INSERT INTO trades (internal_trade_id, broker_pos_id, symbol, candidate_uid, side, entry_price, entry_ts, entry_bar_id, horizon_bars, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')",
            [internal_id, broker_pos_id, symbol.upper(), candidate_uid, side, float(entry_price), entry_ts, entry_bar_id, horizon],
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
        exit_price: Optional[float] = None,
        exit_ts: Optional[datetime] = None,
        pnl_pips: Optional[float] = None,
    ) -> None:
        """Update a trade status and exit data (CLOSED/CANCELLED)."""
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

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()
