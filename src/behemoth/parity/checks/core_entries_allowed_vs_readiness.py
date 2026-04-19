"""Seed check: entry_blocked_not_ready events must correlate with non-READY readiness."""
from __future__ import annotations

import json

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


@register_check(surface_id="core.entries_allowed_vs_readiness", severity="high")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="present",
            evidence="",
        )
    readiness_path = ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json"
    if not readiness_path.exists():
        return CheckResult(
            passed=True, severity="high",
            observed="no readiness snapshot — nothing to cross-check",
            expected="readiness states match blocked-entry events",
            evidence="",
        )
    readiness_blob = json.loads(readiness_path.read_text() or "{}")
    ready_by_symbol: dict[str, str] = {}
    for entry in readiness_blob.get("symbols", []):
        sym = str(entry.get("symbol") or "").upper()
        state = str(entry.get("state") or "").upper()
        if sym:
            ready_by_symbol[sym] = state
    offenders: list[str] = []
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        blocked = df[df["event_name"] == "entry_blocked_not_ready"]
        if blocked.empty:
            continue
        state = ready_by_symbol.get(symbol, "UNKNOWN")
        if state == "READY":
            offenders.append(f"{symbol}: {len(blocked)} blocked events while state=READY")
    if offenders:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(offenders),
            expected="entry_blocked_not_ready only while state != READY",
            evidence=str(readiness_path),
        )
    return CheckResult(
        passed=True, severity="high",
        observed="all entry_blocked_not_ready events correlate with non-READY states",
        expected="entry_blocked_not_ready only while state != READY",
        evidence="",
    )
