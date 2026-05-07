"""Bar-level barrier manager for completed-bar OCO touch confirmation.

Produces identical signal selection, side determination, and lifecycle blocking
as _oco_precompute in scripts/build_tick_opportunity_ml_dataset.py.
Touch confirmation is completed-bar based; the live adapter then submits a
market order immediately after confirmation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import duckdb

from src.behemoth.core.schemas import BarContext, BarrierAction, BarrierActionType

_CREATE_BARRIER_SCANS_SQL = """
CREATE TABLE IF NOT EXISTS barrier_scans (
    scan_id VARCHAR PRIMARY KEY,
    symbol VARCHAR NOT NULL,
    candidate_uid VARCHAR NOT NULL,
    signal_bar_idx INTEGER NOT NULL,
    ref_price DOUBLE NOT NULL,
    signal_close_ask DOUBLE,
    signal_close_bid DOUBLE,
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
        self._con.execute(
            "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_ask DOUBLE"
        )
        self._con.execute(
            "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_bid DOUBLE"
        )

    def close(self) -> None:
        if self._owns_con:
            self._con.close()

    def register_scan(
        self,
        symbol: str,
        candidate_uid: str,
        signal_bar_idx: int,
        barrier_pips: float,
        horizon: int,
        pip_size: float,
        pred_prob: float,
        threshold: float,
        model_month: str,
        reservation_id: str | None,
        run_id: str | None,
        ref_price: float | None = None,
        signal_close_ask: float | None = None,
        signal_close_bid: float | None = None,
    ) -> str:
        """Register a new barrier scan. Called when selected_exec=1 passes all gates."""
        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        explicit_mode = signal_close_ask is not None or signal_close_bid is not None
        if explicit_mode:
            if signal_close_ask is None or signal_close_bid is None:
                raise ValueError(
                    "register_scan requires both signal_close_ask and signal_close_bid "
                    "when using explicit side-aware inputs"
                )
            if ref_price is None:
                ref_price = signal_close_bid
        else:
            if ref_price is None:
                raise ValueError(
                    "register_scan requires ref_price or explicit signal_close_ask/signal_close_bid"
                )
            signal_close_ask = ref_price
            signal_close_bid = ref_price
        upper = signal_close_ask + barrier_pips * pip_size
        lower = signal_close_bid - barrier_pips * pip_size
        self._con.execute(
            """INSERT INTO barrier_scans (
                scan_id, symbol, candidate_uid, signal_bar_idx,
                ref_price, signal_close_ask, signal_close_bid,
                upper_barrier, lower_barrier, barrier_pips, horizon,
                scan_bars_remaining, status, pred_prob, threshold,
                model_month, reservation_id, run_id, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCANNING', ?, ?, ?, ?, ?, ?)""",
            [
                scan_id, symbol.upper(), candidate_uid, signal_bar_idx,
                ref_price, signal_close_ask, signal_close_bid, upper, lower, barrier_pips, horizon,
                horizon, pred_prob, threshold,
                model_month, reservation_id, run_id,
                datetime.now(tz=timezone.utc),
            ],
        )
        return scan_id

    def reject_legacy_active_scans(self) -> list[dict[str, str | None]]:
        """Expire active scans that predate the side-aware signal close columns.

        Legacy scans cannot be reconstructed safely because the stored reference
        price alone does not encode whether the scan should anchor off close_ask
        or close_bid. Rejecting them on startup prevents stale barriers from
        surviving a restart on a persistent DB.
        """
        rows = self._con.execute(
            "SELECT scan_id, symbol, candidate_uid, reservation_id "
            "FROM barrier_scans "
            "WHERE status IN ('SCANNING', 'HOLDING') "
            "AND (signal_close_ask IS NULL OR signal_close_bid IS NULL)"
        ).fetchall()
        rejected = [
            {
                "scan_id": row[0],
                "symbol": row[1],
                "candidate_uid": row[2],
                "reservation_id": row[3],
            }
            for row in rows
        ]
        if not rejected:
            return []
        self._con.execute(
            "UPDATE barrier_scans "
            "SET scan_bars_remaining = 0, hold_bars_remaining = 0, status = 'EXPIRED' "
            "WHERE status IN ('SCANNING', 'HOLDING') "
            "AND (signal_close_ask IS NULL OR signal_close_bid IS NULL)"
        )
        return rejected

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

    def evaluate_bar(self, bar_context: BarContext) -> list[BarrierAction]:
        """Evaluate a completed bar against all active scans for this symbol.

        Called on every bar completion. Mirrors _oco_precompute barrier detection:
        - Checks bar_high_ask >= upper_barrier (up touch) and bar_low_bid <= lower_barrier (dn touch)
        - If both touched same bar: uses bar_hl_first to break tie (positive = high first = BUY)
        - Returns list of action dicts: OPEN_MARKET for new touches, CLOSE_MARKET for completed holds
        - Touch confirmation is completed-bar based; the live adapter submits a
          market order immediately after touch confirmation
        """
        symbol = bar_context.symbol
        bar_ticks = bar_context.bar_ticks
        bar_high_bid = bar_context.bid.high
        bar_low_bid = bar_context.bid.low
        bar_hl_first = bar_context.hl_first
        current_bar_idx = bar_context.bar_idx
        bar_high_ask = bar_context.ask.high
        sym = symbol.upper()
        actions: list[BarrierAction] = []

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
            up_touch = bar_high_ask >= upper
            dn_touch = bar_low_bid <= lower
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
                        actions.append(self._release_reservation_action(
                            symbol=sym,
                            candidate_uid=candidate_uid,
                            scan_id=scan_id,
                            reservation_id=reservation_id,
                        ))
                    continue
                self._transition_to_holding(scan_id, touch_step, side, horizon)
                actions.append(self._open_market_action(
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    scan_id=scan_id,
                    side=side,
                    reservation_id=reservation_id,
                    horizon=horizon,
                ))
            elif up_touch:
                self._transition_to_holding(scan_id, touch_step, "BUY", horizon)
                actions.append(self._open_market_action(
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    scan_id=scan_id,
                    side="BUY",
                    reservation_id=reservation_id,
                    horizon=horizon,
                ))
            elif dn_touch:
                self._transition_to_holding(scan_id, touch_step, "SELL", horizon)
                actions.append(self._open_market_action(
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    scan_id=scan_id,
                    side="SELL",
                    reservation_id=reservation_id,
                    horizon=horizon,
                ))
            elif bars_rem <= 0:
                self._con.execute(
                    "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED' WHERE scan_id = ?",
                    [scan_id],
                )
                if reservation_id is not None:
                    actions.append(self._release_reservation_action(
                        symbol=sym,
                        candidate_uid=candidate_uid,
                        scan_id=scan_id,
                        reservation_id=reservation_id,
                    ))
            else:
                self._con.execute(
                    "UPDATE barrier_scans SET scan_bars_remaining = ? WHERE scan_id = ?",
                    [bars_rem, scan_id],
                )

        # Process HOLDING scans (only those already in HOLDING before this bar, not newly transitioned)
        newly_transitioned = {a.scan_id for a in actions if a.type == BarrierActionType.OPEN_MARKET}
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
                actions.append(BarrierAction(
                    type=BarrierActionType.CLOSE_MARKET,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    broker_pos_id=broker_pos_id,
                    scan_id=scan_id,
                ))
            else:
                self._con.execute(
                    "UPDATE barrier_scans SET hold_bars_remaining = ? WHERE scan_id = ?",
                    [hold_rem, scan_id],
                )

        return actions

    @staticmethod
    def _open_market_action(
        *,
        symbol: str,
        candidate_uid: str,
        scan_id: str,
        side: str,
        reservation_id: str | None,
        horizon: int,
    ) -> BarrierAction:
        return BarrierAction(
            type=BarrierActionType.OPEN_MARKET,
            symbol=symbol,
            candidate_uid=candidate_uid,
            scan_id=scan_id,
            side=side,
            reservation_id=reservation_id,
            horizon=horizon,
        )

    @staticmethod
    def _release_reservation_action(
        *,
        symbol: str,
        candidate_uid: str,
        scan_id: str,
        reservation_id: str | None,
    ) -> BarrierAction:
        return BarrierAction(
            type=BarrierActionType.RELEASE_RESERVATION,
            symbol=symbol,
            candidate_uid=candidate_uid,
            scan_id=scan_id,
            reservation_id=reservation_id,
        )

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
