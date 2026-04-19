"""Seed check: every predict failure is either warmup-skip or classified critically.

If a predict_failure row exists with detail that is NOT 'Insufficient warmup bars',
that is a silent non-warmup failure and the check fails.
"""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


@register_check(surface_id="failure.predict_422_warmup_only", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence="",
        )
    offenders: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        fails = df[df["event_name"] == "predict_failure"]
        for _, row in fails.iterrows():
            detail = str(row.get("detail") or "")
            if "Insufficient warmup bars" not in detail:
                offenders.append(f"{symbol}: {detail[:80]}")
    if offenders:
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(offenders[:5]),
            expected="every predict_failure detail contains 'Insufficient warmup bars'",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{checked} symbols scanned, no non-warmup predict failures",
        expected="every predict_failure detail contains 'Insufficient warmup bars'",
        evidence="",
    )
