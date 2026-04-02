"""Bar-level barrier manager — detects barrier touches using completed bar OHLC.

Produces identical signal selection, side determination, and lifecycle blocking
as _oco_precompute in scripts/build_tick_opportunity_ml_dataset.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import duckdb

_CREATE_BARRIER_SCANS_SQL = """
CREATE TABLE IF NOT EXISTS barrier_scans (
    scan_id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    candidate_uid VARCHAR NOT NULL,
    signal_bar_idx INTEGER NOT NULL,
    ref_price DOUBLE NOT NULL,
    upper_barrier DOUBLE NOT NULL,
    lower_barrier DOUBLE NOT NULL,
    barrier_pips DOUBLE NOT NULL,
    horizon INTEGER NOT NULL,
    scan_bars_remaining INTEGER NOT NULL,
    touch_step INTEGER,
    touch_side VARCHAR,
    hold_bars_remaining INTEGER,
    status VARCHAR NOT NULL,
    broker_pos_id VARCHAR,
    pred_prob DOUBLE,
    threshold DOUBLE,
    model_month VARCHAR,
    reservation_id VARCHAR,
    run_id VARCHAR,
    created_ts TIMESTAMPTZ NOT NULL
);
"""


class BarrierManager:
    """Manages pending barrier scans and active positions.

    State lifecycle: SCANNING -> HOLDING -> COMPLETED
                     SCANNING -> EXPIRED (no touch within horizon)
    """

    def __init__(self, *, con: duckdb.DuckDBPyConnection | None = None) -> None:
        if con is not None:
            self._con = con
            self._owns_con = False
        else:
            self._con = duckdb.connect()
            self._owns_con = True
        self._con.execute(_CREATE_BARRIER_SCANS_SQL)

    def close(self) -> None:
        if self._owns_con:
            self._con.close()

    def register_scan(
        self,
        symbol: str,
        candidate_uid: str,
        signal_bar_idx: int,
        ref_price: float,
        barrier_pips: float,
        horizon: int,
        pip_size: float,
        pred_prob: float,
        threshold: float,
        model_month: str,
        reservation_id: str | None,
        run_id: str | None,
    ) -> str:
        """Register a new barrier scan. Called when selected_exec=1 passes all gates."""
        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        upper = ref_price + barrier_pips * pip_size
        lower = ref_price - barrier_pips * pip_size
        self._con.execute(
            """INSERT INTO barrier_scans (
                scan_id, symbol, candidate_uid, signal_bar_idx,
                ref_price, upper_barrier, lower_barrier, barrier_pips, horizon,
                scan_bars_remaining, status, pred_prob, threshold,
                model_month, reservation_id, run_id, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCANNING', ?, ?, ?, ?, ?, ?)""",
            [
                scan_id, symbol.upper(), candidate_uid, signal_bar_idx,
                ref_price, upper, lower, barrier_pips, horizon,
                horizon, pred_prob, threshold,
                model_month, reservation_id, run_id,
                datetime.now(tz=timezone.utc),
            ],
        )
        return scan_id

    def has_active_scan(self, symbol: str, candidate_uid: str) -> bool:
        """Check if candidate has an active (SCANNING or HOLDING) scan."""
        res = self._con.execute(
            "SELECT COUNT(*) FROM barrier_scans WHERE symbol = ? AND candidate_uid = ? AND status IN ('SCANNING', 'HOLDING')",
            [symbol.upper(), candidate_uid],
        ).fetchone()
        return res is not None and res[0] > 0

    def get_scan(self, scan_id: str) -> dict | None:
        """Retrieve a scan record by ID. Used for testing and diagnostics."""
        res = self._con.execute(
            "SELECT * FROM barrier_scans WHERE scan_id = ?", [scan_id]
        ).fetchone()
        if res is None:
            return None
        cols = [desc[0] for desc in self._con.description]
        return dict(zip(cols, res))
