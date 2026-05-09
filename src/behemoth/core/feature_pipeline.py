"""Deep feature pipeline: accepts DataFrame, returns ModelFeatures or None.

Owns warmup checking, schema validation, and feature computation.
"""

from __future__ import annotations

import pandas as pd

from src.behemoth.core.features import (
    CURRENT_FEATURE_SCHEMA,
    FeatureConfig,
    compute_features_from_bars,
    compute_regime_quantiles_from_bars,
)
from src.behemoth.core.schemas import ModelFeatures


class FeaturePipeline:
    """Self-contained feature computation pipeline.

    Interface:
        compute(df, symbol, bar_ticks, horizon, barrier_pips) -> ModelFeatures | None
        compute_regime_quantiles(df, symbol) -> dict[str, float]
    """

    def __init__(self, config: FeatureConfig | None = None) -> None:
        self._cfg = config or FeatureConfig()
        self._warmup_bars = self._cfg.full_warmup_bars

    @property
    def warmup_bars(self) -> int:
        return self._warmup_bars

    @property
    def config(self) -> FeatureConfig:
        return self._cfg

    def compute(
        self,
        df: pd.DataFrame,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        if len(df) < self._warmup_bars:
            return None
        features = compute_features_from_bars(
            df, symbol=symbol, bar_ticks=bar_ticks, horizon=horizon,
            barrier_pips=barrier_pips, cfg=self._cfg,
        )
        if features is not None:
            self._validate(features)
        return features

    def compute_regime_quantiles(self, df: pd.DataFrame, symbol: str) -> dict[str, float]:
        if len(df) < self._warmup_bars:
            return {}
        return compute_regime_quantiles_from_bars(df, symbol=symbol, cfg=self._cfg)

    def _validate(self, features: ModelFeatures) -> None:
        observed = tuple(type(features).model_fields)
        if observed != CURRENT_FEATURE_SCHEMA.feature_names:
            raise ValueError(
                f"Feature count drift: expected {CURRENT_FEATURE_SCHEMA.feature_names}, got {observed}"
            )
        for name, value in features.model_dump().items():
            if isinstance(value, float):
                if value != value:  # NaN
                    raise ValueError(f"NaN detected in feature '{name}'")
                if value == float("inf") or value == float("-inf"):
                    raise ValueError(f"Inf detected in feature '{name}'")

    def to_dict(self) -> dict:
        return {
            "vol_window": self._cfg.vol_window,
            "cost_window": self._cfg.cost_window,
            "schema_version": self._cfg.schema.version,
            "warmup_bars": self._warmup_bars,
            "min_periods_vol": self._cfg.min_periods_vol,
            "min_periods_cost": self._cfg.min_periods_cost,
        }
