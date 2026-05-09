"""Test HorizonAwareFeatureConfig — per-horizon rolling windows."""

import pytest

from src.behemoth.core.horizon_feature_config import (
    HorizonAwareFeatureConfig,
    HorizonWindowsConfig,
)


class TestHorizonWindowsConfig:
    """Test HorizonWindowsConfig dataclass."""

    def test_config_creation(self) -> None:
        """Create a horizon window config."""
        cfg = HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288)
        assert cfg.horizon == 6
        assert cfg.vol_window == 96
        assert cfg.cost_window == 288

    def test_config_is_frozen(self) -> None:
        """HorizonWindowsConfig is immutable."""
        cfg = HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288)
        with pytest.raises(AttributeError):
            cfg.vol_window = 48


class TestHorizonAwareFeatureConfig:
    """Test adaptive per-horizon feature config."""

    def test_default_config_has_standard_horizons(self) -> None:
        """Default config includes h=2,4,6,12,24."""
        cfg = HorizonAwareFeatureConfig()
        horizons = cfg.all_horizons()
        assert 2 in horizons
        assert 4 in horizons
        assert 6 in horizons
        assert 12 in horizons
        assert 24 in horizons

    def test_get_exact_horizon(self) -> None:
        """Getting exact horizon returns configured values."""
        cfg = HorizonAwareFeatureConfig()
        win = cfg.get_window_config(6)
        assert win.horizon == 6
        assert win.vol_window == 96
        assert win.cost_window == 288

    def test_get_intermediate_horizon_fallback(self) -> None:
        """Intermediate horizons fall back to closest smaller horizon."""
        cfg = HorizonAwareFeatureConfig()
        # h=8 not in config; should fallback to h=6
        win = cfg.get_window_config(8)
        assert win.horizon == 6  # Fallback

        # h=10 not in config; should fallback to h=6
        win = cfg.get_window_config(10)
        assert win.horizon == 6

    def test_get_large_horizon_fallback(self) -> None:
        """Very large horizons fall back to largest configured."""
        cfg = HorizonAwareFeatureConfig()
        # h=100 not in config; should fallback to h=24 (largest)
        win = cfg.get_window_config(100)
        assert win.horizon == 24

    def test_get_horizon_smaller_than_all(self) -> None:
        """Horizons smaller than min configured fall back to min."""
        cfg = HorizonAwareFeatureConfig()
        # h=1 not in config; should fallback to h=2 (smallest)
        win = cfg.get_window_config(1)
        assert win.horizon == 2

    def test_custom_horizon_windows(self) -> None:
        """Initialize with custom per-horizon config."""
        custom = {
            5: HorizonWindowsConfig(horizon=5, vol_window=64, cost_window=128),
            10: HorizonWindowsConfig(horizon=10, vol_window=80, cost_window=200),
        }
        cfg = HorizonAwareFeatureConfig(horizon_windows=custom)
        win = cfg.get_window_config(5)
        assert win.vol_window == 64
        assert win.cost_window == 128

    def test_short_horizon_uses_smaller_windows(self) -> None:
        """Short horizons use smaller windows (lower warmup)."""
        cfg = HorizonAwareFeatureConfig()
        h2 = cfg.get_window_config(2)
        h6 = cfg.get_window_config(6)
        # h=2 should have smaller or equal windows to h=6
        assert h2.vol_window <= h6.vol_window
        assert h2.cost_window <= h6.cost_window

    def test_warmup_bars_h2_smaller_than_h6(self) -> None:
        """Short horizon warmup is smaller (lower latency)."""
        cfg = HorizonAwareFeatureConfig()
        warmup_h2 = cfg.get_warmup_bars(2)
        warmup_h6 = cfg.get_warmup_bars(6)
        assert warmup_h2 <= warmup_h6

    def test_warmup_bars_with_custom_lag(self) -> None:
        """Warmup respects custom lag parameter."""
        cfg = HorizonAwareFeatureConfig()
        warmup_lag1 = cfg.get_warmup_bars(6, lag_bars=1)
        warmup_lag2 = cfg.get_warmup_bars(6, lag_bars=2)
        assert warmup_lag2 == warmup_lag1 + 1

    def test_all_horizons_sorted(self) -> None:
        """all_horizons() returns sorted list."""
        cfg = HorizonAwareFeatureConfig()
        horizons = cfg.all_horizons()
        assert horizons == sorted(horizons)

    def test_validate_horizon_known(self) -> None:
        """validate_horizon passes for configured horizons."""
        cfg = HorizonAwareFeatureConfig()
        # Should not raise
        cfg.validate_horizon(6)
        cfg.validate_horizon(12)

    def test_validate_horizon_unknown_raises(self) -> None:
        """validate_horizon raises for unconfigured horizons."""
        cfg = HorizonAwareFeatureConfig()
        with pytest.raises(ValueError, match="not configured"):
            cfg.validate_horizon(999)

    def test_get_window_config_invalid_horizon_raises(self) -> None:
        """get_window_config rejects horizon <= 0."""
        cfg = HorizonAwareFeatureConfig()
        with pytest.raises(ValueError, match="must be > 0"):
            cfg.get_window_config(0)
        with pytest.raises(ValueError, match="must be > 0"):
            cfg.get_window_config(-5)

    def test_horizon_windows_config_equality(self) -> None:
        """HorizonWindowsConfig values can be compared."""
        cfg1 = HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288)
        cfg2 = HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288)
        assert cfg1 == cfg2

    def test_horizon_windows_config_inequality(self) -> None:
        """Different configs are not equal."""
        cfg1 = HorizonWindowsConfig(horizon=6, vol_window=96, cost_window=288)
        cfg2 = HorizonWindowsConfig(horizon=6, vol_window=48, cost_window=144)
        assert cfg1 != cfg2
