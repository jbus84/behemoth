
from src.behemoth.api.runtime_app_state import RuntimeAppState


class TestGetAppState:
    def test_get_app_state_returns_runtime_app_state(self) -> None:
        from src.behemoth.api.server import _get_app_state
        state = _get_app_state()
        assert isinstance(state, RuntimeAppState)
