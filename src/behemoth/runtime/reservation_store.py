"""DuckDB-backed reservation storage with write-through cache and audit trail."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.behemoth.risk.account import ReservationState, ReservationStateMachine
from src.behemoth.risk.reservation_lifecycle import ReservationLifecycle
from src.behemoth.runtime.state_store import StateStore

logger = logging.getLogger("behemoth.runtime.reservation_store")

_CREATE_SQL = [
    """
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
    source VARCHAR,
    family VARCHAR
);
""",
    """
CREATE TABLE IF NOT EXISTS account_risk_reservation_audit (
    reservation_id VARCHAR NOT NULL,
    event_ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    from_status VARCHAR,
    to_status VARCHAR NOT NULL,
    reason VARCHAR,
    broker_pos_id VARCHAR
);
""",
    """
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
    reservation_id VARCHAR,
    family VARCHAR
);
""",
]

_INSERT_SQL = (
    "INSERT INTO account_risk_reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_ALLOC_EVENT_INSERT_SQL = (
    "INSERT INTO account_risk_allocator_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


@dataclass(frozen=True)
class ReservationSnapshot:
    """Immutable read-only view of a reservation."""

    reservation_id: str
    created_ts: datetime
    updated_ts: datetime
    symbol: str
    candidate_uid: str
    broker_pos_id: str | None
    status: str
    reserved_loss_ccy: float
    barrier_pips: float
    cap_pips: float
    cost_est_pips: float
    volume_units: float
    side: str | None
    source: str
    family: str | None = None


class ReservationStore:
    """Owns reservation lifecycle: DB writes, cache updates, audit trail."""

    def __init__(self, store: StateStore) -> None:
        self._store = store
        for ddl in _CREATE_SQL:
            self._store.execute(ddl)
        self._lifecycle_cache: dict[str, ReservationLifecycle] = {}

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
        family: str | None = None,
    ) -> str:
        initial_state = ReservationStateMachine.validate_initial(status)
        rid = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc)
        self._store.execute(
            _INSERT_SQL,
            [
                rid, now_utc, now_utc, symbol.upper(), candidate_uid, None,
                initial_state.value, float(reserved_loss_ccy), float(barrier_pips),
                float(cap_pips), float(cost_est_pips), float(volume_units),
                side, source, family,
            ],
        )
        self._write_audit_event(
            reservation_id=rid, from_status=None, to_status=initial_state.value,
            reason=f"created_from_{source}", broker_pos_id=None,
        )
        self._lifecycle_cache[rid] = ReservationLifecycle(
            reservation_id=rid, initial_state=initial_state, loss_ccy=reserved_loss_ccy,
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
        row = self._store.execute(
            "SELECT status FROM account_risk_reservations WHERE reservation_id = ? LIMIT 1",
            [reservation_id],
        ).fetchone()
        if row is None:
            raise KeyError(f"reservation not found: {reservation_id}")
        current_status = str(row[0])
        target = ReservationStateMachine.validate_transition(current_status, target_status)
        self._write_audit_event(
            reservation_id=reservation_id, from_status=current_status,
            to_status=target.value, reason=reason, broker_pos_id=broker_pos_id,
        )
        now_utc = datetime.now(timezone.utc)
        safe_reason = str(reason or "").replace("|", "_").replace("'", "_")
        if safe_reason:
            self._store.execute(
                """
                UPDATE account_risk_reservations
                SET status = ?, broker_pos_id = COALESCE(?, broker_pos_id),
                    updated_ts = ?, source = source || ?
                WHERE reservation_id = ?
                """,
                [target.value, broker_pos_id, now_utc, f"|{safe_reason}", reservation_id],
            )
        else:
            self._store.execute(
                """
                UPDATE account_risk_reservations
                SET status = ?, broker_pos_id = COALESCE(?, broker_pos_id), updated_ts = ?
                WHERE reservation_id = ?
                """,
                [target.value, broker_pos_id, now_utc, reservation_id],
            )
        lifecycle = self._lifecycle_cache.get(reservation_id)
        if lifecycle is not None:
            if target == ReservationState.OPEN:
                lifecycle.open_position(broker_pos_id=broker_pos_id)
            elif target == ReservationState.CLOSED:
                lifecycle.close_position()
            elif target == ReservationState.RELEASED:
                lifecycle.release(reason=reason or "released")
            elif target == ReservationState.EXPIRED:
                lifecycle.expire()
        return target.value

    def release_account_risk_reservation(
        self,
        *,
        reservation_id: str | None = None,
        broker_pos_id: str | None = None,
        candidate_uid: str | None = None,
        symbol: str | None = None,
        reason: str = "released",
    ) -> int:
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
        rows = self._store.execute(
            f"SELECT reservation_id FROM account_risk_reservations WHERE {where_sql}",
            params,
        ).fetchall()
        if not rows:
            return 0
        for row in rows:
            self.transition_account_risk_reservation(
                str(row[0]), ReservationState.RELEASED, reason=reason,
            )
        return len(rows)

    def expire_stale_account_risk_pending_reservations(self, *, max_age_seconds: int) -> int:
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc.timestamp() - float(max_age_seconds)
        cutoff_ts = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        rows = self._store.execute(
            "SELECT reservation_id FROM account_risk_reservations WHERE status = 'PENDING' AND created_ts < ?",
            [cutoff_ts],
        ).fetchall()
        if not rows:
            return 0
        for row in rows:
            self.transition_account_risk_reservation(
                str(row[0]), ReservationState.EXPIRED, reason="stale_pending",
            )
        return len(rows)

    def sum_active_account_risk_reserved_loss_ccy(
        self, *, symbol: str | None = None, include_pending: bool = True, include_open: bool = True, family: str | None = None,
    ) -> float:
        statuses: list[str] = []
        if include_pending:
            statuses.append("PENDING")
        if include_open:
            statuses.append("OPEN")
        if not statuses:
            return 0.0
        placeholders = ",".join(["?"] * len(statuses))
        params: list[Any] = list(statuses)
        query = f"SELECT COALESCE(SUM(reserved_loss_ccy), 0.0) FROM account_risk_reservations WHERE status IN ({placeholders})"
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if family:
            query += " AND family = ?"
            params.append(family)
        row = self._store.execute(query, params).fetchone()
        if not row or row[0] is None:
            return 0.0
        return float(row[0])

    def list_active_account_risk_reservations(self, *, symbol: str | None = None, family: str | None = None) -> list[ReservationSnapshot]:
        params: list[Any] = []
        query = """
            SELECT reservation_id, created_ts, updated_ts, symbol, candidate_uid, broker_pos_id,
                   status, reserved_loss_ccy, barrier_pips, cap_pips, cost_est_pips, volume_units,
                   side, source, family
            FROM account_risk_reservations
            WHERE status IN ('PENDING', 'OPEN')
        """
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if family:
            query += " AND family = ?"
            params.append(family)
        query += " ORDER BY created_ts ASC"
        rows = self._store.execute(query, params).fetchall()
        out: list[ReservationSnapshot] = []
        for r in rows:
            out.append(ReservationSnapshot(
                reservation_id=str(r[0]),
                created_ts=_to_utc(r[1]),
                updated_ts=_to_utc(r[2]),
                symbol=str(r[3]),
                candidate_uid=str(r[4]),
                broker_pos_id=r[5],
                status=str(r[6]),
                reserved_loss_ccy=float(r[7]),
                barrier_pips=float(r[8]),
                cap_pips=float(r[9]),
                cost_est_pips=float(r[10]),
                volume_units=float(r[11]),
                side=r[12],
                source=str(r[13]),
                family=r[14],
            ))
        return out

    def log_account_risk_allocator_event(
        self, *, symbol: str, candidate_uid: str, status: str, block_reason: str | None,
        reserved_loss_ccy: float | None, requested_volume_units: float, pred_prob: float,
        threshold_exec: float, risk_rank_score: float | None, reservation_id: str | None,
        family: str | None = None,
    ) -> None:
        now_utc = datetime.now(timezone.utc)
        self._store.execute(
            _ALLOC_EVENT_INSERT_SQL,
            [
                now_utc, symbol.upper(), candidate_uid, str(status).upper(), block_reason,
                float(reserved_loss_ccy) if reserved_loss_ccy is not None else None,
                float(requested_volume_units), float(pred_prob), float(threshold_exec),
                float(risk_rank_score) if risk_rank_score is not None else None,
                reservation_id, family,
            ],
        )

    def get_reservation_audit_trail(self, reservation_id: str) -> list[dict] | None:
        db_rows = self._store.execute(
            """
            SELECT from_status, to_status, event_ts, reason, broker_pos_id
            FROM account_risk_reservation_audit
            WHERE reservation_id = ?
            ORDER BY event_ts ASC
            """,
            [reservation_id],
        ).fetchall()
        if db_rows:
            return [
                {"from_status": row[0], "to_status": row[1], "event_ts": row[2],
                 "reason": row[3], "broker_pos_id": row[4]}
                for row in db_rows
            ]
        lifecycle = self._lifecycle_cache.get(reservation_id)
        if lifecycle is not None:
            audit = lifecycle.to_dict()
            transitions = audit.get("transitions", [])
            for transition in transitions:
                self._write_audit_event(
                    reservation_id=reservation_id,
                    from_status=transition.get("from_status"),
                    to_status=transition.get("to_status"),
                    reason=transition.get("reason"),
                    broker_pos_id=transition.get("broker_pos_id"),
                )
            return transitions
        return None

    def _write_audit_event(
        self, *, reservation_id: str, from_status: str | None, to_status: str,
        reason: str | None = None, broker_pos_id: str | None = None,
    ) -> None:
        self._store.execute(
            """
            INSERT INTO account_risk_reservation_audit
            (reservation_id, event_ts, from_status, to_status, reason, broker_pos_id)
            VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            """,
            [reservation_id, from_status, to_status, reason, broker_pos_id],
        )


def _to_utc(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    return datetime.now(timezone.utc)
