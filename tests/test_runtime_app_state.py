"""Tests for the RuntimeAppState container."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from src.behemoth.api.runtime_app_state import RuntimeAppState


def test_default_construction_has_all_optionals_unset() -> None:
    state = RuntimeAppState()
    assert state.state is None
    assert state.barrier_manager is None
    assert state.orchestrator is None
    assert state.registry is None
    assert state.historical_registry is None
    assert state.account_risk_profile is None
    assert state.aggregators == {}
    assert state.feed_state == {}
    assert state.models_dir == Path("models/oco")
    assert state.account_risk_rules_path == Path("")
    assert state.historical_entries_loaded == 0
    assert state.lifespan_ready is False


def test_default_aggregators_and_feed_state_are_independent_per_instance() -> None:
    """``field(default_factory=...)`` must produce a fresh dict per instance,
    not a shared mutable default. Easy bug to introduce; pin it."""
    a = RuntimeAppState()
    b = RuntimeAppState()
    a.aggregators[100] = "sentinel"  # type: ignore[assignment]
    a.feed_state["EURUSD"] = {"ticks": 1}
    assert b.aggregators == {}
    assert b.feed_state == {}


def test_is_ready_false_until_orchestrator_state_and_lifespan_ready() -> None:
    state = RuntimeAppState()
    assert state.is_ready() is False

    state.state = mock.MagicMock()
    assert state.is_ready() is False  # missing orchestrator

    state.orchestrator = mock.MagicMock()
    assert state.is_ready() is False  # lifespan not yet ready

    state.lifespan_ready = True
    assert state.is_ready() is True


def test_app_state_singleton_in_server_module_is_synced_at_startup() -> None:
    """Smoke test: importing server.py exposes a default ``_app_state`` so
    routes can reference it without crashing during module import. Lifespan
    populates the fields; this test only checks the import contract."""
    from src.behemoth.api import server

    assert isinstance(server._app_state, RuntimeAppState)
    # Before lifespan runs, the container is in default state
    assert server._app_state.lifespan_ready is False
