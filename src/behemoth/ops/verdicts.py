from __future__ import annotations

from enum import Enum


class ProcessVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class SymbolDecision(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"


class RestartEligibility(str, Enum):
    RESTART_ELIGIBLE = "RESTART_ELIGIBLE"
    RESTART_ELIGIBLE_DRAIN_ONLY = "RESTART_ELIGIBLE_DRAIN_ONLY"
    RESTART_BLOCKED = "RESTART_BLOCKED"


def _clean(value: str) -> str:
    return str(value).strip().upper().replace("-", "_")


def normalize_process_verdict(value: str) -> ProcessVerdict:
    cleaned = _clean(value)
    if cleaned == "PASS":
        return ProcessVerdict.PASS
    if cleaned == "FAIL":
        return ProcessVerdict.FAIL
    raise ValueError(f"invalid process verdict: {value!r}; expected PASS or FAIL")


def normalize_symbol_decision(value: str) -> SymbolDecision:
    cleaned = _clean(value)
    if cleaned == "GO":
        return SymbolDecision.GO
    if cleaned in {"NO_GO", "NOGO"}:
        return SymbolDecision.NO_GO
    raise ValueError(f"invalid symbol decision: {value!r}; expected GO or NO_GO")


def normalize_restart_eligibility(value: str) -> RestartEligibility:
    cleaned = _clean(value)
    if cleaned in {"RESTART_ELIGIBLE", "ELIGIBLE"}:
        return RestartEligibility.RESTART_ELIGIBLE
    if cleaned in {"RESTART_ELIGIBLE_DRAIN_ONLY", "DRAIN_ONLY"}:
        return RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    if cleaned in {"RESTART_BLOCKED", "BLOCKED"}:
        return RestartEligibility.RESTART_BLOCKED
    raise ValueError(
        f"invalid restart eligibility: {value!r}; expected RESTART_ELIGIBLE, "
        "RESTART_ELIGIBLE_DRAIN_ONLY, or RESTART_BLOCKED"
    )
