"""Tests for core.entries_allowed_vs_readiness."""
from __future__ import annotations

import json

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import core_entries_allowed_vs_readiness  # noqa: F401


def _write_events(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_readiness(path, entries):
    path.write_text(json.dumps({"symbols": entries}))


def test_blocked_entry_with_not_ready_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    _write_events(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "entry_blocked_not_ready",
             "pass": "false", "detail": "entries not allowed"},
        ],
    )
    _write_readiness(
        ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json",
        [{"symbol": "EURUSD", "state": "WARMING_UP"}],
    )
    result = registry.call("core.entries_allowed_vs_readiness", ctx)
    assert result.passed is True


def test_blocked_entry_while_ready_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    _write_events(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "entry_blocked_not_ready",
             "pass": "false", "detail": "entries not allowed"},
        ],
    )
    _write_readiness(
        ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json",
        [{"symbol": "EURUSD", "state": "READY"}],
    )
    result = registry.call("core.entries_allowed_vs_readiness", ctx)
    assert result.passed is False
