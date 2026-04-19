"""Tests for lifecycle.active_oco_reconciled."""
from __future__ import annotations

import json

import duckdb

from behemoth.parity import registry
from behemoth.parity.checks import lifecycle_active_oco_reconciled  # noqa: F401


def _prime_db(db_path) -> None:
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE barrier_scans (scan_id VARCHAR, symbol VARCHAR, status VARCHAR)"
    )
    con.execute(
        "INSERT INTO barrier_scans VALUES ('scan_a', 'EURUSD', 'HOLDING')"
    )
    con.close()


def test_matching_json_and_db_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _prime_db(ctx.live_state_db_path)
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    (ctx.reconcile_dir / "runtime" / "active_oco_state.json").write_text(
        json.dumps([{"scan_id": "scan_a", "symbol": "EURUSD", "status": "HOLDING"}])
    )
    result = registry.call("lifecycle.active_oco_reconciled", ctx)
    assert result.passed is True


def test_orphan_in_json_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _prime_db(ctx.live_state_db_path)
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    (ctx.reconcile_dir / "runtime" / "active_oco_state.json").write_text(
        json.dumps([
            {"scan_id": "scan_a", "symbol": "EURUSD", "status": "HOLDING"},
            {"scan_id": "scan_missing", "symbol": "EURUSD", "status": "HOLDING"},
        ])
    )
    result = registry.call("lifecycle.active_oco_reconciled", ctx)
    assert result.passed is False
    assert "scan_missing" in result.observed
