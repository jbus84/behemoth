"""Warmup boundary verification: replaces silent None returns with observable status."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WarmupStatus:
    """Result of a warmup bar count check."""

    ok: bool
    bar_count: int
    required: int
    deficit: int  # 0 when ok


class WarmupBoundaryVerifier:
    """Single source of truth for warmup gate decisions."""

    def __init__(self, warmup_bars: int) -> None:
        """Initialize verifier with the required warmup bar count."""
        self._required = warmup_bars

    def check(self, bar_count: int) -> WarmupStatus:
        """Check if bar_count satisfies warmup requirement.

        Args:
            bar_count: Number of bars available.

        Returns:
            WarmupStatus with ok=True if bar_count >= required, deficit=0.
            Otherwise ok=False with deficit = (required - bar_count).
        """
        deficit = max(0, self._required - bar_count)
        return WarmupStatus(
            ok=(deficit == 0),
            bar_count=bar_count,
            required=self._required,
            deficit=deficit,
        )
