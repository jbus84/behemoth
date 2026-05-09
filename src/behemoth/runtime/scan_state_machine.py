"""Scan State Machine — explicit barrier scan lifecycle and transitions."""

from __future__ import annotations

from enum import Enum


class ScanState(str, Enum):
    """Barrier scan states through its lifecycle."""

    SCANNING = "SCANNING"  # Initial: actively looking for barrier touch
    HOLDING = "HOLDING"  # Touch detected: waiting for price action
    COMPLETED = "COMPLETED"  # Position filled and closed
    RELEASED = "RELEASED"  # Reservation released without filling
    EXPIRED = "EXPIRED"  # Timeout or regime change


class ScanStateMachine:
    """Type-safe barrier scan state transitions.

    Enforces the valid state machine for OCO scans:
    - SCANNING → HOLDING (on barrier touch) | EXPIRED (on timeout)
    - HOLDING → COMPLETED (on entry) | RELEASED (on manual cancel) | HOLDING (continue)
    - Terminal states: COMPLETED, RELEASED, EXPIRED (no further transitions)
    """

    # Allowed transitions: state → set of valid target states
    VALID_TRANSITIONS = {
        ScanState.SCANNING: frozenset({ScanState.HOLDING, ScanState.EXPIRED}),
        ScanState.HOLDING: frozenset({ScanState.COMPLETED, ScanState.RELEASED}),
        ScanState.COMPLETED: frozenset(),  # Terminal
        ScanState.RELEASED: frozenset(),  # Terminal
        ScanState.EXPIRED: frozenset(),  # Terminal
    }

    INITIAL_STATES = frozenset({ScanState.SCANNING})

    @classmethod
    def validate_transition(cls, current: ScanState | str, target: ScanState | str) -> ScanState:
        """Validate and normalize a state transition.

        Args:
            current: Current state (ScanState or string)
            target: Target state (ScanState or string)

        Returns:
            Normalized target state as ScanState

        Raises:
            ValueError: If transition is invalid
        """
        curr = ScanState(current) if isinstance(current, str) else current
        targ = ScanState(target) if isinstance(target, str) else target

        if targ not in cls.VALID_TRANSITIONS.get(curr, frozenset()):
            raise ValueError(
                f"Invalid scan state transition: {curr.value} → {targ.value}. "
                f"Valid transitions from {curr.value}: {[s.value for s in cls.VALID_TRANSITIONS.get(curr, frozenset())]}"
            )
        return targ

    @classmethod
    def validate_initial(cls, state: ScanState | str) -> ScanState:
        """Validate that a state is allowed as an initial state.

        Args:
            state: State to validate (ScanState or string)

        Returns:
            Normalized state as ScanState

        Raises:
            ValueError: If state is not a valid initial state
        """
        s = ScanState(state) if isinstance(state, str) else state
        if s not in cls.INITIAL_STATES:
            raise ValueError(
                f"Invalid initial scan state: {s.value}. "
                f"Valid initial states: {[s.value for s in cls.INITIAL_STATES]}"
            )
        return s

    @classmethod
    def is_terminal(cls, state: ScanState | str) -> bool:
        """Check if a state is terminal (no further transitions allowed)."""
        s = ScanState(state) if isinstance(state, str) else state
        return len(cls.VALID_TRANSITIONS.get(s, frozenset())) == 0
