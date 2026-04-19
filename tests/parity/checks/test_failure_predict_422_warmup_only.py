"""Tests for failure.predict_422_warmup_only."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import failure_predict_422_warmup_only  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_only_warmup_failures_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_warmup_skipped",
             "pass": "true", "detail": "Insufficient warmup bars"},
        ],
    )
    result = registry.call("failure.predict_422_warmup_only", ctx)
    assert result.passed is True


def test_non_warmup_422_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_failure",
             "pass": "false", "detail": "HTTP 422: model artifact mismatch"},
        ],
    )
    result = registry.call("failure.predict_422_warmup_only", ctx)
    assert result.passed is False
    assert "model artifact mismatch" in result.observed
