"""Tests for failure.tick_batch_599_fallback_consistency."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import failure_tick_batch_599_fallback  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_no_fallback_rows_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "true", "detail": "accepted=50;attempt=1"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is True


def test_fallback_without_success_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "false", "detail": "mode=single_tick_fallback;accepted=0"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is False


def test_fallback_with_accepted_but_pass_false_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "false", "detail": "mode=single_tick_fallback;accepted=10"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is False
    assert "pass=false" in result.observed


def test_prefixed_accepted_key_is_not_matched(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "true", "detail": "mode=single_tick_fallback;not_accepted=0;accepted=5"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is True
