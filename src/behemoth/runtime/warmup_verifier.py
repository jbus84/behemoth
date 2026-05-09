"""Warmup boundary verification: replaces silent None returns with observable status."""

from __future__ import annotations

from dataclasses import dataclass

from src.behemoth.core.features import FeatureConfig


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

    def validate_warmup_parity(self, feature_config: FeatureConfig) -> None:
        """Assert that verifier requirement matches FeatureConfig computation.

        Args:
            feature_config: Feature configuration to validate against.

        Raises:
            ValueError: If verifier's required bars != config's full_warmup_bars.
        """
        expected = feature_config.full_warmup_bars
        if self._required != expected:
            raise ValueError(
                f"Warmup parity violation: WarmupBoundaryVerifier requires {self._required} bars, "
                f"but FeatureConfig.full_warmup_bars computes {expected}. "
                f"Check FeatureComputationEngine initialization and FeatureConfig.lag_bars."
            )
