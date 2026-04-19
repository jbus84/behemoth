"""Tests for time_data.bar_close_ts_sorted_per_symbol."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import time_data_bar_close_ts_sorted  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_monotonic_bar_close_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:00:00Z"},
            {"event_ts_utc": "2026-04-15T09:01:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:01:00Z"},
        ],
    )
    result = registry.call("time_data.bar_close_ts_sorted_per_symbol", ctx)
    assert result.passed is True


def test_out_of_order_bar_close_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:01:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:01:00Z"},
            {"event_ts_utc": "2026-04-15T09:02:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:00:00Z"},
        ],
    )
    result = registry.call("time_data.bar_close_ts_sorted_per_symbol", ctx)
    assert result.passed is False
