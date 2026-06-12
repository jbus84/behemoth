from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    SET = "SET"                          # floor >= cost: stage set, build the model
    EXECUTION_GATED = "EXECUTION_GATED"  # floor < cost <= ceiling: needs tick-exact maker check
    NOGO = "NOGO"                        # ceiling < cost, or A/B/FDR failed


def classify(structure: bool, reversion: bool, fdr_pass: bool,
             floor: float, ceiling: float, cost: float,
             floor_multiple: float = 1.0) -> Verdict:
    """Apply the A/B/C band gate for one spread at one cost (markup) level."""
    if not (structure and reversion and fdr_pass):
        return Verdict.NOGO
    if floor >= floor_multiple * cost:
        return Verdict.SET
    if ceiling >= cost:
        return Verdict.EXECUTION_GATED
    return Verdict.NOGO
