"""Seed check: every single-tick fallback produced a matching accepted count."""
from __future__ import annotations

import re

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_ACCEPTED_RE = re.compile(r"accepted=(\d+)")


@register_check(
    surface_id="failure.tick_batch_599_fallback_consistency",
    severity="high",
)
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence="",
        )
    bad: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        fallback = df[df["detail"].astype(str).str.contains(
            "single_tick_fallback", na=False
        )]
        for _, row in fallback.iterrows():
            match = _ACCEPTED_RE.search(str(row.get("detail") or ""))
            accepted = int(match.group(1)) if match else 0
            passed_flag = str(row.get("pass", "")).strip().lower()
            if accepted == 0 or passed_flag == "false":
                bad.append(
                    f"{symbol}@{row['event_ts_utc']} fallback accepted={accepted} "
                    f"pass={passed_flag}"
                )
    if bad:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(bad[:5]) + (f" (+{len(bad)-5} more)" if len(bad) > 5 else ""),
            expected="every single_tick_fallback event has accepted>0 and pass=true",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="high",
        observed=f"{checked} symbols scanned, fallback rows consistent",
        expected="every single_tick_fallback event has accepted>0 and pass=true",
        evidence="",
    )
