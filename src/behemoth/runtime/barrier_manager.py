"""Bar-level barrier manager for completed-bar OCO touch confirmation.

Produces identical signal selection, side determination, and lifecycle blocking
as _oco_precompute in scripts/build_tick_opportunity_ml_dataset.py.
Touch confirmation is completed-bar based; the live adapter then submits a
market order immediately after confirmation.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from src.behemoth.core.schemas import BarContext, BarrierAction, BarrierActionType
from src.behemoth.runtime.bar_touch_semantics import BarTouchSemantics
from src.behemoth.runtime.scan_state_machine import ScanState, ScanStateMachine
from src.behemoth.runtime.barrier_context import (
    BarContextAdapter,
    BarrierEvaluationContext,
)
from src.behemoth.runtime.state_store import StateStore, DuckDBStateStore

T = TypeVar("T")

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


@dataclass(frozen=True)
class BarrierStateMutation:
    """Explicit side-effect performed while evaluating a completed bar."""

    scan_id: str
    from_status: str
    to_status: str
    reason: str


@dataclass(frozen=True)
class BarrierEvaluationResult:
    """Completed-bar evaluation output including actions and state mutations."""

    actions: list[BarrierAction]
    mutations: list[BarrierStateMutation]


class BarrierManager:
    """Manages pending barrier scans and active positions.

    State lifecycle: SCANNING -> HOLDING -> COMPLETED
                     SCANNING -> EXPIRED (no touch within horizon)
    """

    def __init__(self, *, store: StateStore | None = None) -> None:
        if store is not None:
            self._store = store
            self._owns_store = False
        else:
            self._store = DuckDBStateStore()
            self._owns_store = True
        # Execute DDL via the underlying connection (DuckDBStateStore provides raw_connection)
        if hasattr(self._store, 'raw_connection'):
            con = self._store.raw_connection()  # type: ignore
            con.execute(_CREATE_BARRIER_SCANS_SQL)
            con.execute(
                "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_ask DOUBLE"
            )
            con.execute(
                "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_bid DOUBLE"
            )
        else:
            # For stores that don't support raw DDL, execute via execute() method
            self._store.execute(_CREATE_BARRIER_SCANS_SQL)
            for ddl in [
                "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_ask DOUBLE",
                "ALTER TABLE barrier_scans ADD COLUMN IF NOT EXISTS signal_close_bid DOUBLE",
            ]:
                try:
                    self._store.execute(ddl)
                except Exception:
                    # SQLite and other stores may not support IF NOT EXISTS on ALTER TABLE
                    pass

    def close(self) -> None:
        if self._owns_store:
            self._store.close()

    def _with_transaction(self, fn: Callable[[], T]) -> T:
        """Execute fn within a state store transaction.

        On exception, rolls back and re-raises. Ensures atomicity of multi-statement
        operations without caller-side transaction management.
        """
        try:
            self._store.begin()
            result = fn()
            self._store.commit()
            return result
        except Exception:
            self._store.rollback()
            raise

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

        def _do_register() -> str:
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            upper = signal_close_ask + barrier_pips * pip_size
            lower = signal_close_bid - barrier_pips * pip_size
            self._store.execute(
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
        return self._with_transaction(_do_register)

    def reject_legacy_active_scans(self) -> list[dict[str, str | None]]:
        """Expire active scans that predate the side-aware signal close columns.

        Legacy scans cannot be reconstructed safely because the stored reference
        price alone does not encode whether the scan should anchor off close_ask
        or close_bid. Rejecting them on startup prevents stale barriers from
        surviving a restart on a persistent DB.
        """
        rows = self._store.execute(
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
        self._store.execute(
            "UPDATE barrier_scans "
            "SET scan_bars_remaining = 0, hold_bars_remaining = 0, status = 'EXPIRED' "
            "WHERE status IN ('SCANNING', 'HOLDING') "
            "AND (signal_close_ask IS NULL OR signal_close_bid IS NULL)"
        )
        return rejected

    def has_active_scan(self, symbol: str, candidate_uid: str) -> bool:
        """Check if candidate has an active (SCANNING or HOLDING) scan."""
        res = self._store.execute(
            "SELECT COUNT(*) FROM barrier_scans WHERE symbol = ? AND candidate_uid = ? AND status IN ('SCANNING', 'HOLDING')",
            [symbol.upper(), candidate_uid],
        ).fetchone()
        return res is not None and res[0] > 0

    def get_scan(self, scan_id: str) -> dict | None:
        """Retrieve a scan record by ID. Used for testing and diagnostics."""
        # Use raw connection if available to get column names
        if hasattr(self._store, 'raw_connection'):
            con = self._store.raw_connection()  # type: ignore
            result = con.execute(
                "SELECT * FROM barrier_scans WHERE scan_id = ?", [scan_id]
            )
            res = result.fetchone()
            if res is None:
                return None
            cols = [desc[0] for desc in result.description]
            return dict(zip(cols, res))
        else:
            # Fallback for stores without raw connection access
            res = self._store.execute(
                "SELECT * FROM barrier_scans WHERE scan_id = ?", [scan_id]
            ).fetchone()
            if res is None:
                return None
            # Column order from CREATE TABLE statement (may not match if columns are missing in test)
            cols = [
                "scan_id", "symbol", "candidate_uid", "signal_bar_idx", "ref_price",
                "signal_close_ask", "signal_close_bid", "upper_barrier", "lower_barrier",
                "barrier_pips", "horizon", "scan_bars_remaining", "touch_step", "touch_side",
                "hold_bars_remaining", "status", "broker_pos_id", "pred_prob", "threshold",
                "model_month", "reservation_id", "run_id", "created_ts"
            ]
            return dict(zip(cols, res))

    def evaluate_bar(self, bar_context: BarContext) -> list[BarrierAction]:
        """Evaluate a completed bar and return broker-facing actions."""
        return self.evaluate_bar_with_result(bar_context).actions

    def evaluate_bar_with_result(self, bar_context: BarContext) -> BarrierEvaluationResult:
        """Evaluate a completed bar against all active scans for this symbol.

        Called on every bar completion. Orchestrates two phases:
        1. Check SCANNING scans for barrier touches, transition touched scans to HOLDING or EXPIRED
        2. Check HOLDING scans for expiration, transition completed holds to COMPLETED

        Returns list of actions (OPEN_MARKET, CLOSE_MARKET, RELEASE_RESERVATION) and state mutations.
        """
        context = BarContextAdapter(bar_context)
        actions: list[BarrierAction] = []
        mutations: list[BarrierStateMutation] = []

        # Phase 1: Process SCANNING scans (check for touches, transition to HOLDING or EXPIRED)
        scanning_actions, scanning_mutations = self._process_scanning_scans(context)
        actions.extend(scanning_actions)
        mutations.extend(scanning_mutations)

        # Phase 2: Process HOLDING scans (check for expiration, transition to COMPLETED)
        holding_actions, holding_mutations = self._process_holding_scans(context, scanning_actions)
        actions.extend(holding_actions)
        mutations.extend(holding_mutations)

        return BarrierEvaluationResult(actions=actions, mutations=mutations)

    def _process_scanning_scans(self, context: BarrierEvaluationContext) -> tuple[list[BarrierAction], list[BarrierStateMutation]]:
        """Process SCANNING scans: check for barrier touches, transition to HOLDING or EXPIRED.

        All updates for this phase are collected into a SQL batch and executed atomically.

        Returns: (actions, mutations) for all SCANNING scans evaluated against the bar.
        """
        symbol = context.symbol
        bar_hl_first = context.hl_first
        current_bar_idx = context.bar_idx
        sym = symbol.upper()
        actions: list[BarrierAction] = []
        mutations: list[BarrierStateMutation] = []
        sql_batch: list[tuple[str, list[Any]]] = []

        scanning = self._store.execute(
            "SELECT scan_id, candidate_uid, upper_barrier, lower_barrier, "
            "scan_bars_remaining, signal_bar_idx, reservation_id, horizon "
            "FROM barrier_scans WHERE symbol = ? AND status = 'SCANNING'",
            [sym],
        ).fetchall()

        for row in scanning:
            (scan_id, candidate_uid, upper, lower,
             bars_rem, signal_bar_idx, reservation_id, horizon) = row

            bars_rem -= 1
            up_touch = context.check_upper_touch(upper)
            dn_touch = context.check_lower_touch(lower)
            touch_step = current_bar_idx - signal_bar_idx

            touch = BarTouchSemantics.evaluate(up_touch, dn_touch, bar_hl_first)

            if touch.decided_side is not None:
                # Validate state transition via state machine
                ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.HOLDING)
                sql_batch.append((
                    "UPDATE barrier_scans SET touch_step = ?, touch_side = ?, "
                    "hold_bars_remaining = ?, status = 'HOLDING' WHERE scan_id = ?",
                    [touch_step, touch.decided_side, horizon, scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="SCANNING", to_status="HOLDING",
                    reason=f"{touch.decided_side.lower()}_touch",
                ))
                actions.append(self._open_market_action(
                    symbol=sym, candidate_uid=candidate_uid, scan_id=scan_id, side=touch.decided_side,
                    reservation_id=reservation_id, horizon=horizon,
                ))
            elif touch.expiry_reason is not None:
                # Validate state transition via state machine
                ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.EXPIRED)
                sql_batch.append((
                    "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED' WHERE scan_id = ?",
                    [scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="SCANNING", to_status="EXPIRED",
                    reason=touch.expiry_reason,
                ))
                if reservation_id is not None:
                    actions.append(self._release_reservation_action(
                        symbol=sym, candidate_uid=candidate_uid, scan_id=scan_id,
                        reservation_id=reservation_id,
                    ))
            elif bars_rem <= 0:
                # Validate state transition via state machine
                ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.EXPIRED)
                sql_batch.append((
                    "UPDATE barrier_scans SET scan_bars_remaining = 0, status = 'EXPIRED' WHERE scan_id = ?",
                    [scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="SCANNING", to_status="EXPIRED",
                    reason="horizon_expired",
                ))
                if reservation_id is not None:
                    actions.append(self._release_reservation_action(
                        symbol=sym, candidate_uid=candidate_uid, scan_id=scan_id,
                        reservation_id=reservation_id,
                    ))
            else:
                sql_batch.append((
                    "UPDATE barrier_scans SET scan_bars_remaining = ? WHERE scan_id = ?",
                    [bars_rem, scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="SCANNING", to_status="SCANNING",
                    reason="scan_decrement",
                ))

        # Execute all scanning-phase updates atomically
        if sql_batch:
            self._with_transaction(lambda: self._execute_batch(sql_batch))

        return actions, mutations

    def _process_holding_scans(self, context: BarrierEvaluationContext, newly_opened_actions: list[BarrierAction]) -> tuple[list[BarrierAction], list[BarrierStateMutation]]:
        """Process HOLDING scans: check for expiration, transition to COMPLETED.

        Skips scans that were just transitioned to HOLDING in this bar (given in newly_opened_actions).
        All updates for this phase are collected into a SQL batch and executed atomically.

        Returns: (actions, mutations) for all HOLDING scans evaluated against the bar.
        """
        symbol = context.symbol
        sym = symbol.upper()
        actions: list[BarrierAction] = []
        mutations: list[BarrierStateMutation] = []
        sql_batch: list[tuple[str, list[Any]]] = []

        # Exclude scans that were just transitioned to HOLDING in this evaluation
        newly_transitioned = {a.scan_id for a in newly_opened_actions if a.type == BarrierActionType.OPEN_MARKET}
        holding = self._store.execute(
            "SELECT scan_id, candidate_uid, broker_pos_id, hold_bars_remaining "
            "FROM barrier_scans WHERE symbol = ? AND status = 'HOLDING'",
            [sym],
        ).fetchall()
        holding = [row for row in holding if row[0] not in newly_transitioned]

        for scan_id, candidate_uid, broker_pos_id, hold_rem in holding:
            hold_rem -= 1
            if hold_rem <= 0:
                sql_batch.append((
                    "UPDATE barrier_scans SET hold_bars_remaining = 0, status = 'COMPLETED' WHERE scan_id = ?",
                    [scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="HOLDING", to_status="COMPLETED",
                    reason="hold_completed",
                ))
                actions.append(BarrierAction(
                    type=BarrierActionType.CLOSE_MARKET,
                    symbol=sym,
                    candidate_uid=candidate_uid,
                    broker_pos_id=broker_pos_id,
                    scan_id=scan_id,
                ))
            else:
                sql_batch.append((
                    "UPDATE barrier_scans SET hold_bars_remaining = ? WHERE scan_id = ?",
                    [hold_rem, scan_id],
                ))
                mutations.append(BarrierStateMutation(
                    scan_id=scan_id, from_status="HOLDING", to_status="HOLDING",
                    reason="hold_decrement",
                ))

        # Execute all holding-phase updates atomically
        if sql_batch:
            self._with_transaction(lambda: self._execute_batch(sql_batch))

        return actions, mutations

    def _execute_batch(self, batch: list[tuple[str, list[Any]]]) -> None:
        """Execute a list of (sql, params) tuples."""
        for sql, params in batch:
            self._store.execute(sql, params)

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
        """Move a scan from SCANNING to HOLDING. Atomic transition ensures consistency."""
        def _do_transition() -> None:
            self._store.execute(
                "UPDATE barrier_scans SET touch_step = ?, touch_side = ?, "
                "hold_bars_remaining = ?, status = 'HOLDING' WHERE scan_id = ?",
                [touch_step, side, horizon, scan_id],
            )
        self._with_transaction(_do_transition)

    def set_broker_pos_id(self, scan_id: str, broker_pos_id: str) -> None:
        """Record the broker position ID after a fill is confirmed."""
        def _do_set() -> None:
            self._store.execute(
                "UPDATE barrier_scans SET broker_pos_id = ? WHERE scan_id = ?",
                [broker_pos_id, scan_id],
            )
        self._with_transaction(_do_set)

    def find_holding_scans(self, symbol: str, candidate_uid: str) -> list[dict]:
        """Find HOLDING scans for a candidate (to link broker_pos_id)."""
        res = self._store.execute(
            "SELECT scan_id, broker_pos_id FROM barrier_scans "
            "WHERE symbol = ? AND candidate_uid = ? AND status = 'HOLDING' "
            "ORDER BY created_ts DESC",
            [symbol.upper(), candidate_uid],
        ).fetchall()
        return [{"scan_id": r[0], "broker_pos_id": r[1]} for r in res]

    def get_scan_by_reservation_id(self, reservation_id: str) -> dict | None:
        """Return the active (SCANNING/HOLDING) scan for a reservation, or None if not found."""
        row = self._store.execute(
            "SELECT scan_id, status FROM barrier_scans "
            "WHERE reservation_id = ? AND status IN ('SCANNING', 'HOLDING') LIMIT 1",
            [reservation_id],
        ).fetchone()
        if row is None:
            return None
        return {"scan_id": row[0], "status": row[1]}
