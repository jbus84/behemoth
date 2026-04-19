"""Tests for the predict_cycles_per_bar check, seeded from 2026-04-17 evidence."""
from __future__ import annotations

from behemoth.parity import registry
from behemoth.parity.checks import core_predict_cycles_per_bar  # noqa: F401
from tests.parity.conftest import write_signal_parity_csv


def test_audusd_2026_04_17_zero_predict_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    write_signal_parity_csv(ctx.reconcile_dir, "AUDUSD",
                             passed=False, predict_cycles=0,
                             failed_signal_events=165)
    write_signal_parity_csv(ctx.reconcile_dir, "EURUSD",
                             passed=True, predict_cycles=136,
                             failed_signal_events=0)

    result = registry.call("core.predict_cycles_per_bar", ctx)
    assert result.passed is False
    assert "AUDUSD" in result.observed
    assert result.severity == "critical"


def test_clean_session_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    write_signal_parity_csv(ctx.reconcile_dir, "EURUSD",
                             passed=True, predict_cycles=136,
                             failed_signal_events=0)

    result = registry.call("core.predict_cycles_per_bar", ctx)
    assert result.passed is True
