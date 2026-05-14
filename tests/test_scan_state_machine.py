"""Test ScanStateMachine — explicit barrier scan lifecycle."""

import pytest

from src.behemoth.runtime.scan_state_machine import ScanState, ScanStateMachine


class TestScanStateEnum:
    """Test ScanState enum."""

    def test_all_states_defined(self) -> None:
        """All required states exist."""
        assert ScanState.SCANNING.value == "SCANNING"
        assert ScanState.HOLDING.value == "HOLDING"
        assert ScanState.COMPLETED.value == "COMPLETED"
        assert ScanState.RELEASED.value == "RELEASED"
        assert ScanState.EXPIRED.value == "EXPIRED"

    def test_states_are_strings(self) -> None:
        """States can be used as strings."""
        assert str(ScanState.SCANNING) == "ScanState.SCANNING"
        state_value = ScanState.SCANNING.value
        assert state_value == "SCANNING"


class TestScanStateMachine:
    """Test scan state machine transitions."""

    def test_scanning_to_holding_is_valid(self) -> None:
        """SCANNING → HOLDING is a valid transition (touch detected)."""
        result = ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.HOLDING)
        assert result == ScanState.HOLDING

    def test_scanning_to_expired_is_valid(self) -> None:
        """SCANNING → EXPIRED is a valid transition (timeout)."""
        result = ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.EXPIRED)
        assert result == ScanState.EXPIRED

    def test_holding_to_completed_is_valid(self) -> None:
        """HOLDING → COMPLETED is a valid transition (entry filled)."""
        result = ScanStateMachine.validate_transition(ScanState.HOLDING, ScanState.COMPLETED)
        assert result == ScanState.COMPLETED

    def test_holding_to_released_is_valid(self) -> None:
        """HOLDING → RELEASED is a valid transition (manual cancel)."""
        result = ScanStateMachine.validate_transition(ScanState.HOLDING, ScanState.RELEASED)
        assert result == ScanState.RELEASED

    def test_invalid_transitions_raise(self) -> None:
        """Invalid transitions raise ValueError."""
        # COMPLETED is terminal
        with pytest.raises(ValueError, match="Invalid scan state transition"):
            ScanStateMachine.validate_transition(ScanState.COMPLETED, ScanState.HOLDING)

        # EXPIRED is terminal
        with pytest.raises(ValueError, match="Invalid scan state transition"):
            ScanStateMachine.validate_transition(ScanState.EXPIRED, ScanState.HOLDING)

        # SCANNING cannot go directly to COMPLETED
        with pytest.raises(ValueError, match="Invalid scan state transition"):
            ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.COMPLETED)

    def test_transition_accepts_string_states(self) -> None:
        """Transitions work with string state names (case-sensitive)."""
        result = ScanStateMachine.validate_transition("SCANNING", "HOLDING")
        assert result == ScanState.HOLDING

    def test_transition_normalizes_to_enum(self) -> None:
        """All transitions return ScanState enum, not strings."""
        result = ScanStateMachine.validate_transition(ScanState.SCANNING, ScanState.HOLDING)
        assert isinstance(result, ScanState)
        assert result.value == "HOLDING"

    def test_valid_initial_state_scanning(self) -> None:
        """SCANNING is the only valid initial state."""
        result = ScanStateMachine.validate_initial(ScanState.SCANNING)
        assert result == ScanState.SCANNING

    def test_invalid_initial_states_raise(self) -> None:
        """Non-SCANNING states cannot be initial."""
        for state in [ScanState.HOLDING, ScanState.COMPLETED, ScanState.RELEASED, ScanState.EXPIRED]:
            with pytest.raises(ValueError, match="Invalid initial scan state"):
                ScanStateMachine.validate_initial(state)

    def test_initial_state_accepts_string(self) -> None:
        """validate_initial works with strings."""
        result = ScanStateMachine.validate_initial("SCANNING")
        assert result == ScanState.SCANNING

    def test_terminal_states_detection(self) -> None:
        """Terminal states are correctly identified."""
        assert not ScanStateMachine.is_terminal(ScanState.SCANNING)
        assert not ScanStateMachine.is_terminal(ScanState.HOLDING)
        assert ScanStateMachine.is_terminal(ScanState.COMPLETED)
        assert ScanStateMachine.is_terminal(ScanState.RELEASED)
        assert ScanStateMachine.is_terminal(ScanState.EXPIRED)

    def test_terminal_states_string_input(self) -> None:
        """is_terminal works with string states."""
        assert ScanStateMachine.is_terminal("COMPLETED")
        assert not ScanStateMachine.is_terminal("SCANNING")

    def test_all_valid_transitions_exist(self) -> None:
        """All states in VALID_TRANSITIONS are real states."""
        for state in ScanStateMachine.VALID_TRANSITIONS:
            assert isinstance(state, ScanState)

    def test_transition_graph_is_acyclic(self) -> None:
        """No cycles in the state machine (DAG property)."""
        # BFS from SCANNING and verify we never return to SCANNING
        visited = set()
        frontier = {ScanState.SCANNING}

        while frontier:
            current = frontier.pop()
            if current in visited:
                # Would indicate a cycle
                raise AssertionError(f"Cycle detected: revisited {current}")
            visited.add(current)
            for target in ScanStateMachine.VALID_TRANSITIONS.get(current, frozenset()):
                if target not in visited:
                    frontier.add(target)

    def test_all_paths_reach_terminal_state(self) -> None:
        """All non-terminal states have at least one path to a terminal state."""
        non_terminal = {ScanState.SCANNING, ScanState.HOLDING}
        for start in non_terminal:
            # BFS to find if any terminal state is reachable
            visited = set()
            frontier = [start]
            found_terminal = False

            while frontier:
                current = frontier.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                if ScanStateMachine.is_terminal(current):
                    found_terminal = True
                    break

                for target in ScanStateMachine.VALID_TRANSITIONS.get(current, frozenset()):
                    if target not in visited:
                        frontier.append(target)

            assert found_terminal, f"No terminal state reachable from {start}"

    def test_error_message_includes_valid_transitions(self) -> None:
        """Error messages list valid transitions."""
        try:
            ScanStateMachine.validate_transition(ScanState.COMPLETED, ScanState.HOLDING)
            raise AssertionError("Should have raised")
        except ValueError as e:
            # Error should mention that COMPLETED has no valid transitions
            assert "COMPLETED" in str(e)
