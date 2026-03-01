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
)
"""

_INSERT_SQL = (
    "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_SQL = """
SELECT row_id, ts, close_ts, open_price, high_price, low_price,
       close_price, spread, tick_volume, hl_first, hl_pos_frac
FROM tick_bars
WHERE symbol = ?
ORDER BY row_id ASC
"""


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

    def append_bar(self, bar: IncomingTickBar) -> None:
        """Append a validated tick bar to the state buffer."""
        sym = bar.symbol.upper()
        idx = self._row_counters.get(sym, 0)
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
        self._row_counters[sym] = idx + 1

    def bar_count(self, symbol: str) -> int:
        """Return the number of bars currently stored for a symbol."""
        r = self._con.execute(
            "SELECT COUNT(*) FROM tick_bars WHERE symbol = ?",
            [symbol.upper()],
        ).fetchone()
        return int(r[0]) if r else 0

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
        n = self.bar_count(sym)
        if n < self._cfg.full_warmup_bars:
            return None

        df = self._con.execute(_SELECT_SQL, [sym]).fetchdf()

        return compute_features_from_bars(
            df,
            symbol=sym,
            bar_ticks=bar_ticks,
            horizon=horizon,
            barrier_pips=barrier_pips,
            cfg=self._cfg,
        )

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._con.close()
