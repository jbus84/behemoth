"""BarTouchSemantics — explicit tie-breaking logic for barrier touches.

Owns the interpretation of hl_first (high-low sequence) for barrier touch decisions:
- hl_first > 0: high touched first → BUY
- hl_first < 0: low touched first → SELL
- hl_first = 0: simultaneous touch → expire with no decision
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarTouchResult:
    """Result of evaluating barrier touches and tie-breaking logic."""

    upper_touched: bool
    """True if upper barrier was touched."""

    lower_touched: bool
    """True if lower barrier was touched."""

    decided_side: str | None
    """'BUY' (upper touched or hl_first > 0), 'SELL' (lower touched or hl_first < 0), or None."""

    expiry_reason: str | None
    """Reason for expiry if no decision (e.g., 'simultaneous_touch_no_hl_first')."""


class BarTouchSemantics:
    """Evaluates barrier touches using explicit hl_first tie-breaking semantics."""

    @staticmethod
    def evaluate(upper_touched: bool, lower_touched: bool, hl_first: float) -> BarTouchResult:
        """Evaluate which barriers touched and apply tie-breaking logic.

        Args:
            upper_touched: Whether upper barrier was touched.
            lower_touched: Whether lower barrier was touched.
            hl_first: Signed value indicating which barrier touched first.
                     Positive = high first, negative = low first, zero = simultaneous.

        Returns:
            BarTouchResult with decided_side and expiry_reason.

        Rules:
            - No touch: return no decision
            - Upper only: BUY
            - Lower only: SELL
            - Both + hl_first > 0 (high first): BUY
            - Both + hl_first < 0 (low first): SELL
            - Both + hl_first == 0 (simultaneous): expire
        """
        if not upper_touched and not lower_touched:
            return BarTouchResult(False, False, None, None)

        if upper_touched and not lower_touched:
            return BarTouchResult(True, False, "BUY", None)

        if lower_touched and not upper_touched:
            return BarTouchResult(False, True, "SELL", None)

        # Both touched — tie-break on hl_first
        if hl_first > 0:
            return BarTouchResult(True, True, "BUY", None)
        if hl_first < 0:
            return BarTouchResult(True, True, "SELL", None)
        return BarTouchResult(True, True, None, "simultaneous_touch_no_hl_first")
