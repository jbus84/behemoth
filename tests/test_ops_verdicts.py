from __future__ import annotations

import pytest

from src.behemoth.ops.verdicts import (
    ProcessVerdict,
    RestartEligibility,
    SymbolDecision,
    normalize_process_verdict,
    normalize_restart_eligibility,
    normalize_symbol_decision,
)


def test_process_verdict_accepts_only_pass_or_fail() -> None:
    assert normalize_process_verdict("PASS") is ProcessVerdict.PASS
    assert normalize_process_verdict("fail") is ProcessVerdict.FAIL

    with pytest.raises(ValueError, match="process verdict"):
        normalize_process_verdict("NO_GO")


def test_symbol_decision_accepts_only_go_or_no_go() -> None:
    assert normalize_symbol_decision("GO") is SymbolDecision.GO
    assert normalize_symbol_decision("no-go") is SymbolDecision.NO_GO

    with pytest.raises(ValueError, match="symbol decision"):
        normalize_symbol_decision("FAIL")


def test_restart_eligibility_names_are_operator_facing() -> None:
    assert normalize_restart_eligibility("restart_eligible") is RestartEligibility.RESTART_ELIGIBLE
    assert (
        normalize_restart_eligibility("RESTART_ELIGIBLE_DRAIN_ONLY")
        is RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY
    )
    assert normalize_restart_eligibility("blocked") is RestartEligibility.RESTART_BLOCKED

    with pytest.raises(ValueError, match="restart eligibility"):
        normalize_restart_eligibility("clean_resumable")
