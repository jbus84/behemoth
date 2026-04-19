"""Seed check: every active_oco_state.json entry has a matching barrier_scans row."""
from __future__ import annotations

import json

import duckdb

from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult


@register_check(surface_id="lifecycle.active_oco_reconciled", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.live_state_db_path is None or not ctx.live_state_db_path.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="live_state.db missing",
            expected="duckdb file present",
            evidence=str(ctx.live_state_db_path),
        )
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="runtime/active_oco_state.json present",
            evidence="",
        )
    with duckdb.connect(str(ctx.live_state_db_path), read_only=True) as con:
        db_ids = {
            row[0] for row in con.execute(
                "SELECT scan_id FROM barrier_scans WHERE status IN ('SCANNING','HOLDING')"
            ).fetchall()
        }
    json_path = ctx.reconcile_dir / "runtime" / "active_oco_state.json"
    if not json_path.exists():
        if not db_ids:
            return CheckResult(
                passed=True, severity="critical",
                observed="no active_oco_state.json and DB has no active scans",
                expected="matching entries between JSON and DB",
                evidence="",
            )
        return CheckResult(
            passed=False, severity="critical",
            observed=f"DB has {len(db_ids)} active scans but active_oco_state.json missing",
            expected="active_oco_state.json present when DB has active scans",
            evidence=str(json_path),
        )
    entries = json.loads(json_path.read_text() or "[]")
    json_ids = {e["scan_id"] for e in entries}
    orphans_in_json = json_ids - db_ids
    orphans_in_db = db_ids - json_ids
    if orphans_in_json or orphans_in_db:
        parts = []
        if orphans_in_json:
            parts.append(f"JSON-only: {sorted(orphans_in_json)}")
        if orphans_in_db:
            parts.append(f"DB-only: {sorted(orphans_in_db)}")
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(parts),
            expected="every active scan appears in both JSON and DB",
            evidence=str(json_path),
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{len(json_ids)} active scans reconciled",
        expected="every active scan appears in both JSON and DB",
        evidence="",
    )
