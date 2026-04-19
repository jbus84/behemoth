"""Seed check: every symbol with bar events must have at least one predict cycle."""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult


@register_check(surface_id="core.predict_cycles_per_bar", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory with *_jforex_signal_parity_summary.csv files",
            evidence=str(ctx.reconcile_dir),
        )
    df = loader.load_signal_parity_csvs(reconcile_dir=ctx.reconcile_dir,
                                         pattern="jforex")
    if df.empty:
        return CheckResult(
            passed=False, severity="critical",
            observed="no signal parity CSVs found",
            expected="at least one CSV",
            evidence=f"glob under {ctx.reconcile_dir}",
        )
    bad = df[(df["predict_cycles"] == 0) & (df["failed_signal_events"] > 0)]
    if not bad.empty:
        offenders = ", ".join(
            f"{row.symbol}({int(row.failed_signal_events)} events)"
            for row in bad.itertuples()
        )
        return CheckResult(
            passed=False, severity="critical",
            observed=f"zero predict cycles with bar events: {offenders}",
            expected="predict_cycles >= 1 wherever failed_signal_events > 0",
            evidence=f"rows in {ctx.reconcile_dir}",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{len(df)} symbols checked; all have predict cycles where bars fired",
        expected="predict_cycles >= 1 wherever failed_signal_events > 0",
        evidence="",
    )
