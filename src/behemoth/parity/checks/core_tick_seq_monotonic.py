"""Seed check: client_tick_seq is strictly monotonic per symbol within a session."""
from __future__ import annotations

import re

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_SEQ_RE = re.compile(r"client_tick_seq=(\d+)")


@register_check(surface_id="core.tick_seq_monotonic", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence=str(ctx.reconcile_dir),
        )
    regressions: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        last = -1
        for _, row in df.iterrows():
            match = _SEQ_RE.search(str(row.get("detail") or ""))
            if not match:
                continue
            seq = int(match.group(1))
            if seq <= last:
                regressions.append(f"{symbol} seq={seq} after {last}")
                break
            last = seq
    if regressions:
        return CheckResult(
            passed=False, severity="critical",
            observed="client_tick_seq regression: " + "; ".join(regressions),
            expected="strictly monotonic client_tick_seq per symbol",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{checked} symbols scanned, no regressions",
        expected="strictly monotonic client_tick_seq per symbol",
        evidence="",
    )
