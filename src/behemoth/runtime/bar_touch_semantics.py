"""Barrier touch semantics: encodes hl_first tie-breaking logic.

Owns the exact semantics of how hl_first (high/low ordering) determines which
side (BUY/SELL) is triggered when both upper and lower barriers touch in the
same bar. Makes barrier evaluation logic explicit and testable.

Convention:
  hl_first > 0  → high came first → BUY side
  hl_first < 0  → low came first → SELL side
  hl_first == 0 → simultaneous or unknown → expire immediately
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BarTouchResult:
    """Result of evaluating barrier touches for a bar."""

    upper_touched: bool
    """Whether the upper (ask) barrier was touched."""

    lower_touched: bool
    """Whether the lower (bid) barrier was touched."""

    decided_side: str | None
    """Which side was decided: 'BUY', 'SELL', or None if no touch or expired."""

    expiry_reason: str | None
    """Reason for expiry if applicable (e.g., 'simultaneous_touch_no_hl_first')."""


class BarTouchSemantics:
    """Owns hl_first interpretation for barrier touch decisions.

    Static methods that evaluate barrier touches and return explicit BarTouchResult
    objects instead of implicit state transitions. This makes the tie-breaking logic
    testable and reusable across different barrier evaluation contexts.
    """

    @staticmethod
    def evaluate(
        upper_touched: bool,
        lower_touched: bool,
        hl_first: float,
    ) -> BarTouchResult:
        """Evaluate barrier touches and determine side/expiry decision.

        Args:
            upper_touched: Whether upper (ask) barrier touched.
            lower_touched: Whether lower (bid) barrier touched.
            hl_first: Sign indicates which touched first (>0: high, <0: low, 0: unknown).

        Returns:
            BarTouchResult with decided_side and optional expiry_reason.
        """
        if not upper_touched and not lower_touched:
            return BarTouchResult(False, False, None, None)

        if upper_touched and not lower_touched:
            return BarTouchResult(True, False, "BUY", None)

        if lower_touched and not upper_touched:
            return BarTouchResult(False, True, "SELL", None)

        # Both touched — use hl_first to break tie
        if hl_first > 0:
            return BarTouchResult(True, True, "BUY", None)
        if hl_first < 0:
            return BarTouchResult(True, True, "SELL", None)

        # Simultaneous touch with no ordering information
        return BarTouchResult(
            True,
            True,
            None,
            "simultaneous_touch_no_hl_first",
        )
