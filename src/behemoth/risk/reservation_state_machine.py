"""Reservation state machine: explicit lifecycle validation.

Manages the finite state machine for account risk reservations:
  PENDING → OPEN → CLOSED
         ↘ RELEASED
         ↘ EXPIRED

All transitions are validated and enforced via ReservationStateMachine.
Raises ReservationTransitionError on invalid edges.
"""

from __future__ import annotations

from enum import Enum


class ReservationTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""

    pass


class ReservationState(str, Enum):
    """Valid states in the reservation lifecycle."""

    PENDING = "PENDING"
    """Reservation created but not yet bound to an order."""

    OPEN = "OPEN"
    """Order filled, position held, capital reserved."""

    CLOSED = "CLOSED"
    """Position closed (exit order filled)."""

    RELEASED = "RELEASED"
    """Reservation released (barrier expired, account risk blocked, etc)."""

    EXPIRED = "EXPIRED"
    """Reservation expired without being opened (horizon expired)."""


class ReservationStateMachine:
    """Validates state transitions in the reservation lifecycle.

    Pure validator — no state mutations here, only transition logic.
    Callers are responsible for persisting state changes.
    """

    VALID_TRANSITIONS: dict[ReservationState, frozenset[ReservationState]] = {
        ReservationState.PENDING: frozenset(
            {ReservationState.OPEN, ReservationState.RELEASED, ReservationState.EXPIRED}
        ),
        ReservationState.OPEN: frozenset(
            {ReservationState.CLOSED, ReservationState.RELEASED}
        ),
        ReservationState.CLOSED: frozenset(),
        ReservationState.RELEASED: frozenset(),
        ReservationState.EXPIRED: frozenset(),
    }

    VALID_INITIAL_STATES = frozenset({ReservationState.PENDING, ReservationState.OPEN})

    @classmethod
    def normalize(cls, raw: str | ReservationState) -> ReservationState:
        """Convert string to ReservationState enum.

        Args:
            raw: String or ReservationState value.

        Returns:
            ReservationState enum.

        Raises:
            ValueError: If raw is not a valid state name.
        """
        if isinstance(raw, ReservationState):
            return raw
        try:
            return ReservationState(raw.upper())
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid reservation state: {raw}") from e

    @classmethod
    def validate_initial(cls, state: str | ReservationState) -> ReservationState:
        """Validate that state is a valid initial state.

        Args:
            state: State to validate (string or enum).

        Returns:
            Normalized ReservationState if valid.

        Raises:
            ReservationTransitionError: If state is not an initial state.
        """
        normalized = cls.normalize(state)
        if normalized not in cls.VALID_INITIAL_STATES:
            raise ReservationTransitionError(
                f"Cannot start reservation in {normalized.value}; valid initial states: "
                f"{', '.join(s.value for s in cls.VALID_INITIAL_STATES)}"
            )
        return normalized

    @classmethod
    def validate_transition(
        cls,
        current: str | ReservationState,
        target: str | ReservationState,
    ) -> ReservationState:
        """Validate a state transition.

        Args:
            current: Current state (string or enum).
            target: Target state (string or enum).

        Returns:
            Normalized target ReservationState if transition is valid.

        Raises:
            ReservationTransitionError: If transition is invalid.
        """
        current_state = cls.normalize(current)
        target_state = cls.normalize(target)
        if target_state not in cls.VALID_TRANSITIONS.get(current_state, frozenset()):
            raise ReservationTransitionError(
                f"invalid reservation transition {current_state.value} -> {target_state.value}"
            )
        return target_state
