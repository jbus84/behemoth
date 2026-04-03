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
    terminal_reason VARCHAR,
    created_ts TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS barrier_scan_events (
    event_seq BIGINT NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    scan_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    candidate_uid VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    detail VARCHAR,
    run_id VARCHAR
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
        self._ensure_schema()

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
        self._record_event(
            scan_id=scan_id,
            symbol=symbol,
            candidate_uid=candidate_uid,
            event_type="SCAN_REGISTERED",
            detail=f"horizon={horizon}; barrier_pips={barrier_pips}",
            run_id=run_id,
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
            "scan_bars_remaining, signal_bar_idx, reservation_id, horizon, run_id "
            "FROM barrier_scans WHERE symbol = ? AND status = 'SCANNING'",
            [sym],
        ).fetchall()

        for row in scanning:
            (scan_id, candidate_uid, upper, lower,
             bars_rem, signal_bar_idx, reservation_id, horizon, run_id) = row

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
                    # hl_first == 0 means undecided; expire immediately with an
                    # explicit terminal reason so the lifecycle remains auditable.
                    self._expire_scan(
                        scan_id,
                        reason="AMBIGUOUS_TOUCH",
                        symbol=sym,
                        candidate_uid=candidate_uid,
                        run_id=run_id,
                    )
                    continue
                self._transition_to_holding(
                    scan_id=scan_id,
                    touch_step=touch_step,
                    side=side,
                    horizon=horizon,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    run_id=run_id,
                )
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": side,
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                })
            elif up_touch:
                self._transition_to_holding(
                    scan_id=scan_id,
                    touch_step=touch_step,
                    side="BUY",
                    horizon=horizon,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    run_id=run_id,
                )
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": "BUY",
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                })
            elif dn_touch:
                self._transition_to_holding(
                    scan_id=scan_id,
                    touch_step=touch_step,
                    side="SELL",
                    horizon=horizon,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    run_id=run_id,
                )
                actions.append({
                    "type": "OPEN_MARKET",
                    "symbol": sym,
                    "side": "SELL",
                    "candidate_uid": candidate_uid,
                    "reservation_id": reservation_id,
                    "scan_id": scan_id,
                })
            elif bars_rem <= 0:
                self._expire_scan(
                    scan_id,
                    reason="NO_TOUCH_WITHIN_HORIZON",
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    run_id=run_id,
                )
            else:
                self._con.execute(
                    "UPDATE barrier_scans SET scan_bars_remaining = ? WHERE scan_id = ?",
                    [bars_rem, scan_id],
                )

        # Process HOLDING scans (only those already in HOLDING before this bar, not newly transitioned)
        newly_transitioned = {a["scan_id"] for a in actions if a["type"] == "OPEN_MARKET"}
        holding = self._con.execute(
            "SELECT scan_id, candidate_uid, broker_pos_id, hold_bars_remaining, run_id "
            "FROM barrier_scans WHERE symbol = ? AND status = 'HOLDING'",
            [sym],
        ).fetchall()
        holding = [row for row in holding if row[0] not in newly_transitioned]

        for scan_id, candidate_uid, broker_pos_id, hold_rem, run_id in holding:
            hold_rem -= 1
            if hold_rem <= 0:
                self._con.execute(
                    "UPDATE barrier_scans SET hold_bars_remaining = 0, status = 'COMPLETED', terminal_reason = 'HOLD_DURATION_ELAPSED' WHERE scan_id = ?",
                    [scan_id],
                )
                self._record_event(
                    scan_id=scan_id,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    event_type="SCAN_COMPLETED",
                    detail=f"broker_pos_id={broker_pos_id}",
                    run_id=run_id,
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

    def mark_open_submission_failed(self, scan_id: str, reason: str) -> None:
        row = self.get_scan(scan_id)
        if row is None or row["status"] != "HOLDING":
            return
        self._con.execute(
            "UPDATE barrier_scans SET status = 'FAILED', terminal_reason = ? WHERE scan_id = ?",
            [reason, scan_id],
        )
        self._record_event(
            scan_id=scan_id,
            symbol=row["symbol"],
            candidate_uid=row["candidate_uid"],
            event_type="OPEN_SUBMISSION_FAILED",
            detail=reason,
            run_id=row["run_id"],
        )

    def list_scan_events(self, scan_id: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT event_seq, event_ts, scan_id, symbol, candidate_uid, event_type, detail, run_id "
            "FROM barrier_scan_events WHERE scan_id = ? ORDER BY event_seq, event_ts",
            [scan_id],
        ).fetchall()
        cols = [desc[0] for desc in self._con.description]
        return [dict(zip(cols, row)) for row in rows]

    def _ensure_schema(self) -> None:
        try:
            self._ensure_table_column("barrier_scans", "terminal_reason", "VARCHAR")
            self._ensure_table_column("barrier_scan_events", "event_seq", "BIGINT")
        except Exception:
            # Best-effort migration only; keep manager usable in ephemeral tests.
            pass

    def _ensure_table_column(self, table_name: str, column_name: str, column_sql: str) -> None:
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
            self._con.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    def _record_event(
        self,
        *,
        scan_id: str,
        symbol: str,
        candidate_uid: str,
        event_type: str,
        detail: str | None,
        run_id: str | None,
    ) -> None:
        seq_row = self._con.execute(
            "SELECT COALESCE(MAX(event_seq), 0) + 1 FROM barrier_scan_events WHERE scan_id = ?",
            [scan_id],
        ).fetchone()
        event_seq = int(seq_row[0]) if seq_row and seq_row[0] is not None else 1
        self._con.execute(
            "INSERT INTO barrier_scan_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                event_seq,
                datetime.now(tz=timezone.utc),
                scan_id,
                symbol.upper(),
                candidate_uid,
                event_type,
                detail,
                run_id,
            ],
        )

    def _expire_scan(
        self,
        scan_id: str,
        *,
        reason: str,
        symbol: str,
        candidate_uid: str,
        run_id: str | None,
    ) -> None:
        self._con.execute(
            "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED', terminal_reason = ? WHERE scan_id = ?",
            [reason, scan_id],
        )
        self._record_event(
            scan_id=scan_id,
            symbol=symbol,
            candidate_uid=candidate_uid,
            event_type="SCAN_EXPIRED",
            detail=reason,
            run_id=run_id,
        )

    def _transition_to_holding(
        self,
        *,
        scan_id: str,
        touch_step: int,
        side: str,
        horizon: int,
        symbol: str,
        candidate_uid: str,
        run_id: str | None,
    ) -> None:
        """Move a scan from SCANNING to HOLDING."""
        self._con.execute(
            "UPDATE barrier_scans SET touch_step = ?, touch_side = ?, "
            "hold_bars_remaining = ?, status = 'HOLDING', terminal_reason = NULL WHERE scan_id = ?",
            [touch_step, side, horizon, scan_id],
        )
        self._record_event(
            scan_id=scan_id,
            symbol=symbol,
            candidate_uid=candidate_uid,
            event_type="SCAN_TOUCH_DETECTED",
            detail=side,
            run_id=run_id,
        )
        self._record_event(
            scan_id=scan_id,
            symbol=symbol,
            candidate_uid=candidate_uid,
            event_type="SCAN_TRANSITIONED_TO_HOLDING",
            detail=f"side={side}; hold_bars_remaining={horizon}; touch_step={touch_step}",
            run_id=run_id,
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
