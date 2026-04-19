"""Check registry for the parity audit harness."""
from __future__ import annotations

from typing import Callable

from behemoth.parity.types import CheckContext, CheckResult, Severity

_Check = Callable[[CheckContext], CheckResult]
_CHECKS: dict[str, tuple[_Check, Severity]] = {}


def register_check(*, surface_id: str, severity: Severity) -> Callable[[_Check], _Check]:
    def _decorator(fn: _Check) -> _Check:
        if surface_id in _CHECKS:
            raise ValueError(f"Check {surface_id!r} already registered")
        _CHECKS[surface_id] = (fn, severity)
        return fn
    return _decorator


def list_registered() -> list[tuple[str, Severity]]:
    return sorted((sid, sev) for sid, (_, sev) in _CHECKS.items())


def call(surface_id: str, ctx: CheckContext) -> CheckResult:
    if surface_id not in _CHECKS:
        raise KeyError(f"surface_id {surface_id!r} not registered")
    fn, _ = _CHECKS[surface_id]
    return fn(ctx)


def all_surface_ids() -> list[str]:
    return sorted(_CHECKS.keys())


def clear_for_tests() -> None:
    """Reset the registry. Tests only."""
    _CHECKS.clear()
