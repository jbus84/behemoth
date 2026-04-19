"""Tests for core.tick_seq_monotonic."""
from __future__ import annotations

from behemoth.parity import registry
from behemoth.parity.checks import core_tick_seq_monotonic  # noqa: F401


def _write_events_csv(path, rows):
    import pandas as pd
    pd.DataFrame(rows).to_csv(path, index=False)


def test_monotonic_seq_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write_events_csv(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=1"},
            {"event_ts_utc": "2026-04-15T09:00:01Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=2"},
        ],
    )
    result = registry.call("core.tick_seq_monotonic", ctx)
    assert result.passed is True


def test_regressing_seq_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write_events_csv(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=2"},
            {"event_ts_utc": "2026-04-15T09:00:01Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=1"},
        ],
    )
    result = registry.call("core.tick_seq_monotonic", ctx)
    assert result.passed is False
    assert "regression" in result.observed.lower()


def test_prefixed_key_is_not_matched(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write_events_csv(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "upstream_client_tick_seq=9"},
            {"event_ts_utc": "2026-04-15T09:00:01Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "upstream_client_tick_seq=8, client_tick_seq=1"},
        ],
    )
    result = registry.call("core.tick_seq_monotonic", ctx)
    assert result.passed is True
