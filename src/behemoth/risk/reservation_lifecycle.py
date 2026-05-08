"""Explicit reservation state machine with audit trail.

Wraps ReservationStateMachine to provide auditable, transactional
reservation lifecycle management. Every state transition is logged
with timestamp and reason for debugging and compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.behemoth.risk.account import ReservationState, ReservationStateMachine


@dataclass(frozen=True)
class ReservationTransition:
    """Immutable record of a state transition."""

    timestamp: datetime
    from_state: ReservationState
    to_state: ReservationState
    reason: str
    context: dict[str, Any] | None = None


class ReservationLifecycle:
    """Manages a single reservation's lifecycle with explicit state transitions.

    Each reservation moves through states: PENDING → OPEN → CLOSED → (terminal)
    or PENDING → RELEASED → (terminal) or PENDING → EXPIRED → (terminal).

    Every transition is logged with timestamp and reason for debugging
    lost or mismatched reservations.

    Usage:
        lifecycle = ReservationLifecycle(
            reservation_id="res_abc123",
            initial_state=ReservationState.PENDING,
            loss_ccy=100.0,
        )
        lifecycle.open_position(broker_pos_id="pos_xyz")  # PENDING → OPEN
        lifecycle.close_position()  # OPEN → CLOSED
        trail = lifecycle.audit_trail()  # Full history
    """

    def __init__(
        self,
        reservation_id: str,
        initial_state: ReservationState | str = ReservationState.PENDING,
        loss_ccy: float | None = None,
    ) -> None:
        """Initialize a new reservation lifecycle.

        Args:
            reservation_id: Unique reservation identifier
            initial_state: Starting state (PENDING or OPEN)
            loss_ccy: Worst-case reserved loss in account currency
        """
        self._reservation_id = str(reservation_id)
        self._loss_ccy = float(loss_ccy) if loss_ccy else 0.0
        self._current_state = ReservationStateMachine.validate_initial(initial_state)
        self._transitions: list[ReservationTransition] = [
            ReservationTransition(
                timestamp=datetime.now(tz=timezone.utc),
                from_state=self._current_state,
                to_state=self._current_state,
                reason="initialization",
                context={"loss_ccy": self._loss_ccy},
            )
        ]

    @property
    def reservation_id(self) -> str:
        """Get the reservation ID."""
        return self._reservation_id

    @property
    def current_state(self) -> ReservationState:
        """Get the current state."""
        return self._current_state

    @property
    def loss_ccy(self) -> float:
        """Get the reserved loss amount in account currency."""
        return self._loss_ccy

    def open_position(self, broker_pos_id: str | None = None) -> None:
        """Transition from PENDING to OPEN (position has been filled).

        Args:
            broker_pos_id: Broker position identifier for the filled position

        Raises:
            ValueError: If transition is invalid from current state
        """
        self._transition(
            target=ReservationState.OPEN,
            reason="position_opened",
            context={"broker_pos_id": broker_pos_id} if broker_pos_id else None,
        )

    def close_position(self) -> None:
        """Transition from OPEN to CLOSED (position has exited).

        Raises:
            ValueError: If transition is invalid from current state
        """
        self._transition(
            target=ReservationState.CLOSED,
            reason="position_closed",
        )

    def release(self, reason: str) -> None:
        """Transition from PENDING or OPEN to RELEASED (capital freed).

        Called when barrier expires, order is rejected, or user cancels.

        Args:
            reason: Why the reservation was released (e.g., 'barrier_expired', 'order_rejected')

        Raises:
            ValueError: If transition is invalid from current state
        """
        self._transition(
            target=ReservationState.RELEASED,
            reason=f"released_{reason}",
        )

    def expire(self) -> None:
        """Transition from PENDING or OPEN to EXPIRED (timeout).

        Called when reservation exceeds TTL without being opened.

        Raises:
            ValueError: If transition is invalid from current state
        """
        self._transition(
            target=ReservationState.EXPIRED,
            reason="expired",
        )

    def _transition(
        self,
        target: ReservationState,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Internal transition logic with validation and logging.

        Args:
            target: Target state
            reason: Reason for transition
            context: Optional context data (e.g., broker_pos_id, rejection_code)

        Raises:
            ValueError: If transition violates state machine rules
        """
        # Validate transition
        validated_target = ReservationStateMachine.validate_transition(
            self._current_state, target
        )

        # Record transition
        transition = ReservationTransition(
            timestamp=datetime.now(tz=timezone.utc),
            from_state=self._current_state,
            to_state=validated_target,
            reason=reason,
            context=context,
        )
        self._transitions.append(transition)

        # Update current state
        self._current_state = validated_target

    def audit_trail(self) -> list[ReservationTransition]:
        """Return immutable audit trail of all state transitions.

        Returns:
            List of transitions in chronological order. First entry is initialization;
            subsequent entries are state changes.
        """
        return list(self._transitions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize lifecycle to dict for persistence or logging.

        Returns:
            Dict containing current state, history, and metadata.
        """
        return {
            "reservation_id": self._reservation_id,
            "current_state": self._current_state.value,
            "loss_ccy": self._loss_ccy,
            "transitions": [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "from_state": t.from_state.value,
                    "to_state": t.to_state.value,
                    "reason": t.reason,
                    "context": t.context,
                }
                for t in self._transitions
            ],
        }
