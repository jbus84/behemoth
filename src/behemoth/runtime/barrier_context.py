"""Barrier evaluation protocol hiding bid/ask side-awareness.

Instead of BarrierManager directly accessing bar_context.bid.low,
bar_context.ask.high, etc., it depends on BarrierEvaluationContext
Protocol. This seam hides side-aware pricing complexity and enables
bar schema refactoring without touching barrier logic.
"""

from __future__ import annotations

from typing import Protocol


class BarrierEvaluationContext(Protocol):
    """Abstract interface for evaluating barriers against a completed bar.

    Implementations encapsulate the bid/ask side-awareness and pricing
    logic. BarrierManager depends on this Protocol, not on the concrete
    BarContext, enabling independent schema evolution.
    """

    @property
    def symbol(self) -> str:
        """Symbol being evaluated (e.g., 'EURUSD')."""
        ...

    @property
    def bar_idx(self) -> int:
        """0-indexed bar number."""
        ...

    @property
    def hl_first(self) -> float:
        """Intra-bar high/low ordering: +1 (high first), -1 (low first), 0 (simultaneous)."""
        ...

    def check_upper_touch(self, upper_barrier: float) -> bool:
        """Check if bar touched or exceeded the upper barrier.

        Upper barriers use ask-side pricing (for BUY entries).
        Returns True if bar's ask-side high >= upper_barrier.

        Args:
            upper_barrier: Upper barrier price (absolute, in instrument units)

        Returns:
            True if upper barrier was touched in this bar
        """
        ...

    def check_lower_touch(self, lower_barrier: float) -> bool:
        """Check if bar touched or fell below the lower barrier.

        Lower barriers use bid-side pricing (for SELL entries).
        Returns True if bar's bid-side low <= lower_barrier.

        Args:
            lower_barrier: Lower barrier price (absolute, in instrument units)

        Returns:
            True if lower barrier was touched in this bar
        """
        ...


class BarContextAdapter:
    """Concrete implementation of BarrierEvaluationContext from BarContext.

    Adapts the full BarContext dataclass to the BarrierEvaluationContext Protocol,
    handling the side-aware pricing logic (ask-side for upper touch, bid-side for lower).
    """

    def __init__(self, bar_context: object) -> None:
        """Initialize adapter with a BarContext object.

        Args:
            bar_context: A BarContext instance (or any object with matching structure)
        """
        # Import here to avoid circular dependency
        from src.behemoth.core.schemas import BarContext

        if not isinstance(bar_context, BarContext):
            raise TypeError(f"Expected BarContext, got {type(bar_context)}")
        self._bar = bar_context

    @property
    def symbol(self) -> str:
        """Get symbol from wrapped BarContext."""
        return self._bar.symbol

    @property
    def bar_idx(self) -> int:
        """Get bar index from wrapped BarContext."""
        return self._bar.bar_idx

    @property
    def hl_first(self) -> float:
        """Get hl_first from wrapped BarContext."""
        return self._bar.hl_first

    def check_upper_touch(self, upper_barrier: float) -> bool:
        """Check upper barrier using ask-side high."""
        return self._bar.ask.high >= upper_barrier

    def check_lower_touch(self, lower_barrier: float) -> bool:
        """Check lower barrier using bid-side low."""
        return self._bar.bid.low <= lower_barrier
