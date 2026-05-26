"""Seed check: every per-symbol live lock pins the expected model_month."""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


def _lock_model_month(lock: dict) -> str | None:
    artifacts = lock.get("artifacts") if isinstance(lock.get("artifacts"), dict) else {}
    historical = (
        lock.get("historical_backtest")
        if isinstance(lock.get("historical_backtest"), dict)
        else {}
    )
    deploy = lock.get("deployability") if isinstance(lock.get("deployability"), dict) else {}
    month = (
        lock.get("model_month")
        or artifacts.get("model_month")
        or deploy.get("model_month")
        or historical.get("target_month")
    )
    return str(month).strip() if month else None


@register_check(surface_id="risk_gov.governance_lock_pin", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.governance_lock_dir is None:
        return CheckResult(
            passed=False, severity="critical",
            observed="governance_lock_dir missing",
            expected="directory with *_live_lock.json files",
            evidence="",
        )
    mismatches: list[str] = []
    missing: list[str] = []
    for symbol in _SYMBOLS:
        lock = loader.load_governance_lock(
            governance_lock_dir=ctx.governance_lock_dir, symbol=symbol
        )
        if not lock:
            missing.append(symbol)
            continue
        lock_model_month = _lock_model_month(lock)
        if lock_model_month != ctx.model_month:
            mismatches.append(
                f"{symbol}: lock={lock_model_month!r} ctx={ctx.model_month!r}"
            )
    if missing or mismatches:
        parts = []
        if missing:
            parts.append(f"missing locks: {', '.join(missing)}")
        if mismatches:
            parts.append(f"month mismatches: {'; '.join(mismatches)}")
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(parts),
            expected=f"every lock pinned to model_month={ctx.model_month}",
            evidence=str(ctx.governance_lock_dir),
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"all {len(_SYMBOLS)} symbols pinned to {ctx.model_month}",
        expected=f"every lock pinned to model_month={ctx.model_month}",
        evidence="",
    )
