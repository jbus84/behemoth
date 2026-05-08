"""Feature computation engine: owns strategy, validation, and computation.

Extracts feature pipeline logic from StateManager to enable:
- Feature strategy swapping (different rolling windows, structural features)
- Independent testing of feature computation without StateManager
- Explicit encapsulation of FeatureConfig + FeatureSchemaValidator
"""

from __future__ import annotations

import pandas as pd

from src.behemoth.core.feature_validator import FeatureSchemaValidator
from src.behemoth.core.features import (
    CURRENT_FEATURE_SCHEMA,
    FeatureConfig,
    compute_features_from_bars,
    compute_regime_quantiles_from_bars,
)
from src.behemoth.core.schemas import ModelFeatures


class FeatureComputationEngine:
    """Owns feature computation strategy: config, validation, and math.

    Encapsulates the feature pipeline so StateManager is reduced to
    persistence + warmup gating. All feature strategy changes concentrated here.
    """

    def __init__(
        self,
        vol_window: int | None = None,
        cost_window: int | None = None,
    ) -> None:
        """Initialize engine with rolling window configuration.

        Args:
            vol_window: Tick-rate/spread z-score window (default: 96 from schema)
            cost_window: Cost median window (default: 288 from schema)
        """
        if vol_window is None:
            vol_window = CURRENT_FEATURE_SCHEMA.rolling_windows["vol_window"]
        if cost_window is None:
            cost_window = CURRENT_FEATURE_SCHEMA.rolling_windows["cost_window"]

        self._cfg = FeatureConfig(vol_window=int(vol_window), cost_window=int(cost_window))
        self._validator = FeatureSchemaValidator()
        self._validator.validate_startup()

    @property
    def warmup_bars(self) -> int:
        """Number of bars required before features can be computed."""
        return self._cfg.full_warmup_bars

    @property
    def config(self) -> FeatureConfig:
        """Access the feature configuration (read-only for inspection)."""
        return self._cfg

    def compute(
        self,
        df: pd.DataFrame,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        """Compute feature vector for latest bar.

        Args:
            df: DataFrame with bars (columns: close_bid, open_bid, high_bid, low_bid,
                close_ts, timestamp, spread, tick_volume, hl_first, hl_pos_frac)
            symbol: Trading symbol
            bar_ticks: Bar size in ticks
            horizon: Bars until strategy exit (for feature context)
            barrier_pips: Distance in pips (for structural features)

        Returns:
            16-feature ModelFeatures or None if insufficient warmup
        """
        features = compute_features_from_bars(
            df,
            symbol=symbol,
            bar_ticks=bar_ticks,
            horizon=horizon,
            barrier_pips=barrier_pips,
            cfg=self._cfg,
        )
        if features is not None:
            self._validator.validate_feature_count(len(features.model_fields))
            self._validator.validate_feature_vector(features)
        return features

    def compute_regime_quantiles(
        self,
        df: pd.DataFrame,
        symbol: str,
    ) -> dict[str, float]:
        """Compute regime gating quantiles for a symbol.

        Args:
            df: DataFrame with bars
            symbol: Trading symbol

        Returns:
            Dict mapping quantile names to threshold values
        """
        return compute_regime_quantiles_from_bars(df, symbol=symbol, cfg=self._cfg)

    def to_dict(self) -> dict:
        """Serialize engine state for logging/diagnostics."""
        return {
            "vol_window": self._cfg.vol_window,
            "cost_window": self._cfg.cost_window,
            "schema_version": self._cfg.schema.version,
            "warmup_bars": self.warmup_bars,
            "min_periods_vol": self._cfg.min_periods_vol,
            "min_periods_cost": self._cfg.min_periods_cost,
        }
