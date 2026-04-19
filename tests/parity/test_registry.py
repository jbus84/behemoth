"""Tests for src/behemoth/parity/registry.py."""
from __future__ import annotations

import pytest

from behemoth.parity import registry
from behemoth.parity.types import CheckContext, CheckResult


def _dummy_ctx() -> CheckContext:
    return CheckContext(
        run_id="test_run",
        model_month="2026-04",
        reconcile_dir=None,
        live_state_db_path=None,
        governance_lock_dir=None,
    )


def test_register_check_stores_callable_by_surface_id():
    registry.clear_for_tests()

    @registry.register_check(surface_id="test.surface", severity="critical")
    def check_foo(ctx: CheckContext) -> CheckResult:
        return CheckResult(passed=True, severity="critical",
                           observed="ok", expected="ok", evidence="")

    assert registry.list_registered() == [("test.surface", "critical")]
    result = registry.call("test.surface", _dummy_ctx())
    assert result.passed is True


def test_register_check_rejects_duplicate_surface_id():
    registry.clear_for_tests()

    @registry.register_check(surface_id="dup", severity="high")
    def _one(ctx): ...

    with pytest.raises(ValueError, match="already registered"):
        @registry.register_check(surface_id="dup", severity="high")
        def _two(ctx): ...


def test_call_unknown_surface_id_raises():
    registry.clear_for_tests()
    with pytest.raises(KeyError, match="not registered"):
        registry.call("does.not.exist", _dummy_ctx())
