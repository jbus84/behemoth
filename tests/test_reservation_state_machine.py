"""Test ReservationStateMachine — explicit state transition validation."""

import pytest

from src.behemoth.risk.reservation_state_machine import (
    ReservationState,
    ReservationStateMachine,
    ReservationTransitionError,
)


class TestReservationStateTransitions:
    """Verify all valid and invalid transitions."""

    def test_pending_to_open_valid(self) -> None:
        """PENDING → OPEN is valid."""
        result = ReservationStateMachine.validate_transition(
            ReservationState.PENDING,
            ReservationState.OPEN,
        )
        assert result == ReservationState.OPEN

    def test_pending_to_released_valid(self) -> None:
        """PENDING → RELEASED is valid."""
        result = ReservationStateMachine.validate_transition(
            ReservationState.PENDING,
            ReservationState.RELEASED,
        )
        assert result == ReservationState.RELEASED

    def test_pending_to_expired_valid(self) -> None:
        """PENDING → EXPIRED is valid."""
        result = ReservationStateMachine.validate_transition(
            ReservationState.PENDING,
            ReservationState.EXPIRED,
        )
        assert result == ReservationState.EXPIRED

    def test_open_to_closed_valid(self) -> None:
        """OPEN → CLOSED is valid."""
        result = ReservationStateMachine.validate_transition(
            ReservationState.OPEN,
            ReservationState.CLOSED,
        )
        assert result == ReservationState.CLOSED

    def test_open_to_released_valid(self) -> None:
        """OPEN → RELEASED is valid."""
        result = ReservationStateMachine.validate_transition(
            ReservationState.OPEN,
            ReservationState.RELEASED,
        )
        assert result == ReservationState.RELEASED

    def test_closed_rejects_all_transitions(self) -> None:
        """CLOSED state rejects all transitions."""
        for target in [
            ReservationState.OPEN,
            ReservationState.RELEASED,
            ReservationState.PENDING,
            ReservationState.EXPIRED,
        ]:
            with pytest.raises(ReservationTransitionError, match="invalid reservation transition"):
                ReservationStateMachine.validate_transition(
                    ReservationState.CLOSED,
                    target,
                )

    def test_released_rejects_all_transitions(self) -> None:
        """RELEASED state rejects all transitions."""
        for target in [
            ReservationState.OPEN,
            ReservationState.PENDING,
            ReservationState.CLOSED,
            ReservationState.EXPIRED,
        ]:
            with pytest.raises(ReservationTransitionError):
                ReservationStateMachine.validate_transition(
                    ReservationState.RELEASED,
                    target,
                )

    def test_expired_rejects_all_transitions(self) -> None:
        """EXPIRED state rejects all transitions."""
        for target in [
            ReservationState.OPEN,
            ReservationState.PENDING,
            ReservationState.CLOSED,
            ReservationState.RELEASED,
        ]:
            with pytest.raises(ReservationTransitionError):
                ReservationStateMachine.validate_transition(
                    ReservationState.EXPIRED,
                    target,
                )

    def test_invalid_transitions_raise_error(self) -> None:
        """All other transitions are invalid."""
        invalid_paths = [
            (ReservationState.PENDING, ReservationState.CLOSED),
            (ReservationState.OPEN, ReservationState.PENDING),
            (ReservationState.OPEN, ReservationState.OPEN),
            (ReservationState.OPEN, ReservationState.EXPIRED),
        ]
        for current, target in invalid_paths:
            with pytest.raises(ReservationTransitionError, match="invalid reservation transition"):
                ReservationStateMachine.validate_transition(current, target)


class TestReservationStateInitialization:
    """Verify initial state validation."""

    def test_pending_is_valid_initial_state(self) -> None:
        """PENDING is a valid initial state."""
        result = ReservationStateMachine.validate_initial(ReservationState.PENDING)
        assert result == ReservationState.PENDING

    def test_open_is_valid_initial_state(self) -> None:
        """OPEN is a valid initial state."""
        result = ReservationStateMachine.validate_initial(ReservationState.OPEN)
        assert result == ReservationState.OPEN

    def test_closed_rejects_as_initial_state(self) -> None:
        """CLOSED cannot be initial state."""
        with pytest.raises(ReservationTransitionError, match="Cannot start reservation"):
            ReservationStateMachine.validate_initial(ReservationState.CLOSED)

    def test_released_rejects_as_initial_state(self) -> None:
        """RELEASED cannot be initial state."""
        with pytest.raises(ReservationTransitionError):
            ReservationStateMachine.validate_initial(ReservationState.RELEASED)

    def test_expired_rejects_as_initial_state(self) -> None:
        """EXPIRED cannot be initial state."""
        with pytest.raises(ReservationTransitionError):
            ReservationStateMachine.validate_initial(ReservationState.EXPIRED)


class TestReservationStateNormalization:
    """Verify state normalization."""

    def test_normalize_uppercase_string(self) -> None:
        """Normalize uppercase string to enum."""
        result = ReservationStateMachine.normalize("PENDING")
        assert result == ReservationState.PENDING

    def test_normalize_lowercase_string(self) -> None:
        """Normalize lowercase string to enum."""
        result = ReservationStateMachine.normalize("pending")
        assert result == ReservationState.PENDING

    def test_normalize_enum_passthrough(self) -> None:
        """Normalize already-enum passthrough."""
        result = ReservationStateMachine.normalize(ReservationState.OPEN)
        assert result == ReservationState.OPEN

    def test_normalize_invalid_state_raises(self) -> None:
        """Normalize invalid state raises ValueError."""
        with pytest.raises(ValueError, match="Invalid reservation state"):
            ReservationStateMachine.normalize("INVALID_STATE")
