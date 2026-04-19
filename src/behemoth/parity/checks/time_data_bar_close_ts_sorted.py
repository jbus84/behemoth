"""Seed check: bar_close timestamps are weakly monotonic per symbol per session."""
from __future__ import annotations

import re

import pandas as pd

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_BAR_CLOSE_RE = re.compile(r"bar_close=([0-9T:Z\-.]+)")


@register_check(surface_id="time_data.bar_close_ts_sorted_per_symbol", severity="high")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="present",
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
        cycles = df[df["event_name"] == "predict_cycle"].copy()
        if cycles.empty:
            continue
        checked += 1
        cycles["bar_close_ts"] = cycles["detail"].apply(
            lambda d: _BAR_CLOSE_RE.search(str(d)).group(1)
            if _BAR_CLOSE_RE.search(str(d)) else None
        )
        cycles = cycles.dropna(subset=["bar_close_ts"])
        if cycles.empty:
            continue
        ts = pd.to_datetime(cycles["bar_close_ts"], utc=True, errors="coerce").dropna()
        if len(ts) < 2:
            continue
        diffs = ts.diff().dt.total_seconds().dropna()
        if (diffs < 0).any():
            negative_count = int((diffs < 0).sum())
            offenders.append(f"{symbol}: {negative_count} out-of-order bar closes")
    if offenders:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(offenders),
            expected="bar_close_ts weakly monotonic per symbol",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="high",
        observed=f"{checked} symbols scanned, bar_close_ts monotonic",
        expected="bar_close_ts weakly monotonic per symbol",
        evidence="",
    )
