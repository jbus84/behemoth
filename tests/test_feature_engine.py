"""Test FeatureComputationEngine extraction from StateManager.

Verify feature computation logic works independently of StateManager.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from src.behemoth.core.feature_engine import FeatureComputationEngine
from src.behemoth.core.schemas import ModelFeatures


class TestFeatureComputationEngine:
    """Verify FeatureComputationEngine encapsulates feature strategy."""

    def test_engine_initialization(self) -> None:
        """Engine initializes with default rolling windows."""
        engine = FeatureComputationEngine()
        assert engine.warmup_bars == 289
        assert engine.config.vol_window == 96
        assert engine.config.cost_window == 288

    def test_engine_custom_windows(self) -> None:
        """Engine accepts custom rolling window parameters."""
        engine = FeatureComputationEngine(vol_window=48, cost_window=144)
        assert engine.config.vol_window == 48
        assert engine.config.cost_window == 144
        # warmup_bars = max(48, 144) + 1 = 145
        assert engine.warmup_bars == 145

    def test_engine_validates_on_startup(self) -> None:
        """Engine validates feature schema at initialization."""
        engine = FeatureComputationEngine()
        # If schema is malformed, initialization would raise ValueError
        # (This passes implicitly if no error is raised)
        assert engine is not None

    def test_compute_returns_none_without_data(self) -> None:
        """compute() returns None on empty DataFrame."""
        engine = FeatureComputationEngine()
        empty_df = pd.DataFrame()
        result = engine.compute(empty_df, "EURUSD", 100, 30, 3.0)
        assert result is None

    def test_compute_regime_quantiles_returns_dict(self) -> None:
        """compute_regime_quantiles() returns dict on valid input."""
        engine = FeatureComputationEngine()
        # Create a minimal DataFrame with required columns
        df = pd.DataFrame({
            "close_bid": [1.1, 1.11, 1.12],
            "open_bid": [1.09, 1.1, 1.11],
            "high_bid": [1.12, 1.13, 1.14],
            "low_bid": [1.08, 1.09, 1.1],
            "close_ts": [datetime.now(tz=timezone.utc)] * 3,
            "timestamp": [datetime.now(tz=timezone.utc)] * 3,
            "spread": [0.0002] * 3,
            "tick_volume": [100.0] * 3,
            "hl_first": [1.0] * 3,
            "hl_pos_frac": [0.5] * 3,
        })
        result = engine.compute_regime_quantiles(df, "EURUSD")
        assert isinstance(result, dict)

    def test_engine_to_dict(self) -> None:
        """to_dict() serializes engine state."""
        engine = FeatureComputationEngine(vol_window=64, cost_window=192)
        state = engine.to_dict()
        assert state["vol_window"] == 64
        assert state["cost_window"] == 192
        assert "schema_version" in state
        assert "warmup_bars" in state


class TestFeatureEngineIntegration:
    """Verify engine works end-to-end with StateManager."""

    def test_state_manager_uses_feature_engine(self) -> None:
        """StateManager delegates feature computation to engine."""
        from src.behemoth.runtime.state import StateManager

        mgr = StateManager()
        # Engine should be initialized
        assert hasattr(mgr, "_feature_engine")
        assert mgr._feature_engine.warmup_bars == 289
        mgr.close()

    def test_feature_computation_still_works(self) -> None:
        """StateManager.compute_features() still returns correct results."""
        from src.behemoth.runtime.state import StateManager

        mgr = StateManager()
        # No bars yet, so should return None
        result = mgr.compute_features("EURUSD", 100, 30, 3.0)
        assert result is None
        mgr.close()

    def test_regime_quantiles_computation_still_works(self) -> None:
        """StateManager.compute_regime_quantiles() still works."""
        from src.behemoth.runtime.state import StateManager

        mgr = StateManager()
        # No bars yet, so should return empty dict
        result = mgr.compute_regime_quantiles("EURUSD", 100)
        assert result == {}
        mgr.close()
