"""Seed check: live_deployable lock present for the active model month per symbol."""
from __future__ import annotations

import json
from pathlib import Path

from behemoth.core.bundle_paths import lock_filename
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

SURFACE_ID = "risk_gov.live_deployable_lock_present_for_active_month"


def _list_deployable_months(history_dir: Path, symbol: str) -> list[str]:
    months: list[str] = []
    if not history_dir.exists():
        return months
    sym_lc = symbol.lower()
    for month_dir in sorted(history_dir.iterdir()):
        if not month_dir.is_dir():
            continue
        lock_path = month_dir / lock_filename(sym_lc, "oco_first_touch")
        if not lock_path.exists():
            continue
        try:
            payload = json.loads(lock_path.read_text())
        except json.JSONDecodeError:
            continue
        deploy = payload.get("deployability") or {}
        deployable = bool(deploy.get("live_deployable", False))
        if deployable:
            months.append(month_dir.name)
    return months


@register_check(SURFACE_ID)
def check(ctx: CheckContext) -> CheckResult:
    failures: list[dict] = []
    for symbol in ctx.symbols:
        active = ctx.active_model_months.get(symbol)
        if active is None:
            continue
        deployable = _list_deployable_months(ctx.history_dir, symbol)
        if active not in deployable:
            failures.append({
                "symbol": symbol,
                "active_model_month": active,
                "available_deployable_months": deployable,
                "detail": (
                    f"No live_deployable=true lock for {symbol} month {active}. "
                    f"available_months={','.join(deployable) or '(none)'}"
                ),
            })
    return CheckResult(
        surface_id=SURFACE_ID,
        passed=not failures,
        failures=failures,
    )
