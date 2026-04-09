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

    def evaluate_bar(
        self,
        symbol: str,
        bar_ticks: int,
        bar_high: float,
        bar_low: float,
        bar_hl_first: float,
        current_bar_idx: int,
    ) -> list[dict]:
        """Evaluate a completed bar against all active scans for this symbol.

        Called on every bar completion. Mirrors _oco_precompute barrier detection:
        - Checks bar_high >= upper_barrier (up touch) and bar_low <= lower_barrier (down touch)
        - If both touched same bar: uses bar_hl_first to break tie (positive = high first = BUY)
        - Returns list of action dicts: OPEN_MARKET for new touches, CLOSE_MARKET for completed holds
        """
        sym = symbol.upper()
        actions: list[dict] = []

        # Process SCANNING scans
        scanning = self._con.execute(
            "SELECT scan_id, candidate_uid, upper_barrier, lower_barrier, "
            "scan_bars_remaining, signal_bar_idx, reservation_id, horizon "
            "FROM barrier_scans WHERE symbol = ? AND status = 'SCANNING'",
            [sym],
        ).fetchall()

        for row in scanning:
            (scan_id, candidate_uid, upper, lower,
             bars_rem, signal_bar_idx, reservation_id, horizon) = row

            bars_rem -= 1
            up_touch = bar_high >= upper
            dn_touch = bar_low <= lower
            touch_step = current_bar_idx - signal_bar_idx

            if up_touch and dn_touch:
                # Both touched — use hl_first to break tie
                if bar_hl_first > 0:
                    side = "BUY"
                elif bar_hl_first < 0:
                    side = "SELL"
                else:
                    # hl_first == 0 means undecided; expire immediately — mirrors
                    # _oco_precompute which locks in side=0 on the first simultaneous
                    # touch and does not evaluate later bars for this signal
                    self._con.execute(
                        "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED' WHERE scan_id = ?",
                        [scan_id],
                    )
                    if reservation_id is not None:
                        actions.append({
                            "type": "RELEASE_RESERVATION",
                            "symbol": sym,
                            "candidate_uid": candidate_uid,
                            "scan_id": scan_id,
                            "reservation_id": reservation_id,
                        })
                    continue
                self._transition_to_holding(scan_id, touch_step, side, horizon)
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": side,
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                    "horizon": horizon,
                })
            elif up_touch:
                self._transition_to_holding(scan_id, touch_step, "BUY", horizon)
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": "BUY",
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                    "horizon": horizon,
                })
            elif dn_touch:
                self._transition_to_holding(scan_id, touch_step, "SELL", horizon)
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": "SELL",
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                    "horizon": horizon,
                })
            elif bars_rem <= 0:
                self._con.execute(
                    "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED' WHERE scan_id = ?",
                    [scan_id],
                )
                if reservation_id is not None:
                    actions.append({
                        "type": "RELEASE_RESERVATION",
                        "symbol": sym,
                        "candidate_uid": candidate_uid,
                        "scan_id": scan_id,
                        "reservation_id": reservation_id,
                    })
            else:
                self._con.execute(
                    "UPDATE barrier_scans SET scan_bars_remaining = ? WHERE scan_id = ?",
                    [bars_rem, scan_id],
                )

        # Process HOLDING scans (only those already in HOLDING before this bar, not newly transitioned)
        newly_transitioned = {a["scan_id"] for a in actions if a["type"] == "OPEN_MARKET"}
        holding = self._con.execute(
            "SELECT scan_id, candidate_uid, broker_pos_id, hold_bars_remaining "
            "FROM barrier_scans WHERE symbol = ? AND status = 'HOLDING'",
            [sym],
        ).fetchall()
        holding = [row for row in holding if row[0] not in newly_transitioned]

        for scan_id, candidate_uid, broker_pos_id, hold_rem in holding:
            hold_rem -= 1
            if hold_rem <= 0:
                self._con.execute(
                    "UPDATE barrier_scans SET hold_bars_remaining = 0, status = 'COMPLETED' WHERE scan_id = ?",
                    [scan_id],
                )
                actions.append({
                    "type": "CLOSE_MARKET",
                    "symbol": sym,
                    "candidate_uid": candidate_uid,
                    "broker_pos_id": broker_pos_id,
                    "scan_id": scan_id,
                })
            else:
                self._con.execute(
                    "UPDATE barrier_scans SET hold_bars_remaining = ? WHERE scan_id = ?",
                    [hold_rem, scan_id],
                )

        return actions

    def _transition_to_holding(self, scan_id: str, touch_step: int, side: str, horizon: int) -> None:
        """Move a scan from SCANNING to HOLDING."""
        self._con.execute(
            "UPDATE barrier_scans SET touch_step = ?, touch_side = ?, "
            "hold_bars_remaining = ?, status = 'HOLDING' WHERE scan_id = ?",
            [touch_step, side, horizon, scan_id],
        )

    def set_broker_pos_id(self, scan_id: str, broker_pos_id: str) -> None:
        """Record the broker position ID after a fill is confirmed."""
        self._con.execute(
            "UPDATE barrier_scans SET broker_pos_id = ? WHERE scan_id = ?",
            [broker_pos_id, scan_id],
        )

    def find_holding_scans(self, symbol: str, candidate_uid: str) -> list[dict]:
        """Find HOLDING scans for a candidate (to link broker_pos_id)."""
        res = self._con.execute(
            "SELECT scan_id, broker_pos_id FROM barrier_scans "
            "WHERE symbol = ? AND candidate_uid = ? AND status = 'HOLDING' "
            "ORDER BY created_ts DESC",
            [symbol.upper(), candidate_uid],
        ).fetchall()
        return [{"scan_id": r[0], "broker_pos_id": r[1]} for r in res]

    def get_scan_by_reservation_id(self, reservation_id: str) -> dict | None:
        """Return the active (SCANNING/HOLDING) scan for a reservation, or None if not found."""
        row = self._con.execute(
            "SELECT scan_id, status FROM barrier_scans "
            "WHERE reservation_id = ? AND status IN ('SCANNING', 'HOLDING') LIMIT 1",
            [reservation_id],
        ).fetchone()
        if row is None:
            return None
        return {"scan_id": row[0], "status": row[1]}
