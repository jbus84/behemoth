"""Horizon-Aware Feature Config — adaptive rolling windows per horizon."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HorizonWindowsConfig:
    """Per-horizon rolling window configuration."""

    horizon: int  # Bar count (e.g., 6, 12, 24)
    vol_window: int  # Volatility rolling window
    cost_window: int  # Cost rolling window


class HorizonAwareFeatureConfig:
    """Adaptive feature configuration that varies rolling windows per horizon.

    Allows:
    - Short horizons (h=2-6) to use smaller windows, reducing warmup delay
    - Longer horizons (h=12+) to use larger windows for stability
    - Explicit tradeoff between latency (small window) and feature precision (large window)
    """

    # Default per-horizon windows: can be overridden per deployment
    DEFAULT_HORIZON_WINDOWS = {
        2: HorizonWindowsConfig(horizon=2, vol_window=48, cost_window=144),
        4: HorizonWindowsConfig(horizon=4, vol_window=64, cost_window=192),
        6: HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288),
        12: HorizonWindowsConfig(horizon=12, vol_window=96, cost_window=288),
        24: HorizonWindowsConfig(horizon=24, vol_window=96, cost_window=288),
    }

    def __init__(self, horizon_windows: dict[int, HorizonWindowsConfig] | None = None) -> None:
        """Initialize with custom or default horizon windows.

        Args:
            horizon_windows: Mapping of horizon → HorizonWindowsConfig.
                            None uses DEFAULT_HORIZON_WINDOWS.
        """
        self._windows = horizon_windows or self.DEFAULT_HORIZON_WINDOWS

    def get_window_config(self, horizon: int) -> HorizonWindowsConfig:
        """Get rolling window config for a specific horizon.

        Falls back to closest known horizon if exact match not found.

        Args:
            horizon: Bar count (e.g., 6, 12)

        Returns:
            HorizonWindowsConfig with vol_window and cost_window

        Raises:
            ValueError: If horizon <= 0
        """
        if horizon <= 0:
            raise ValueError(f"Horizon must be > 0, got {horizon}")

        # Exact match
        if horizon in self._windows:
            return self._windows[horizon]

        # Fallback: use closest smaller horizon, or smallest if all larger
        smaller_horizons = [h for h in self._windows.keys() if h < horizon]
        if smaller_horizons:
            best_horizon = max(smaller_horizons)
        else:
            best_horizon = min(self._windows.keys())

        return self._windows[best_horizon]

    def get_warmup_bars(self, horizon: int, lag_bars: int = 1) -> int:
        """Compute warmup requirement for a given horizon.

        Args:
            horizon: Bar count
            lag_bars: Lag for causality (default 1)

        Returns:
            Minimum bars needed before features are valid
        """
        cfg = self.get_window_config(horizon)
        return max(cfg.vol_window, cfg.cost_window) + lag_bars

    def all_horizons(self) -> list[int]:
        """Return all configured horizons in sorted order."""
        return sorted(self._windows.keys())

    def validate_horizon(self, horizon: int) -> None:
        """Validate that a horizon is supported.

        Raises:
            ValueError: If horizon is not in config
        """
        if horizon not in self._windows:
            known = sorted(self._windows.keys())
            raise ValueError(
                f"Horizon {horizon} not configured. Known horizons: {known}. "
                f"(Will fallback to closest smaller horizon at runtime.)"
            )
