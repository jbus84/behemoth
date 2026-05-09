import pytest
import pandas as pd
from datetime import datetime, timezone
import numpy as np

from src.behemoth.core.feature_pipeline import FeaturePipeline
from src.behemoth.core.schemas import ModelFeatures


def _make_bars(n_rows: int) -> pd.DataFrame:
    base_ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
    close = 1.1000 + np.cumsum(np.full(n_rows, 0.0001))
    return pd.DataFrame({
        "timestamp": [base_ts] * n_rows,
        "close_ts": [base_ts] * n_rows,
        "open_bid": close - 0.00005,
        "high_bid": close + 0.0002,
        "low_bid": close - 0.0002,
        "close_bid": close,
        "spread": np.full(n_rows, 0.0002),
        "tick_volume": np.full(n_rows, 100.0),
        "hl_first": np.ones(n_rows),
        "hl_pos_frac": np.zeros(n_rows),
    })


class TestFeaturePipeline:
    def test_compute_returns_none_for_insufficient_warmup(self) -> None:
        pipeline = FeaturePipeline()
        df = _make_bars(10)
        result = pipeline.compute(df, "EURUSD", 100, 6, 2.0)
        assert result is None

    def test_compute_returns_model_features_for_sufficient_warmup(self) -> None:
        from src.behemoth.core.features import FeatureConfig
        cfg = FeatureConfig()
        pipeline = FeaturePipeline(cfg)
        df = _make_bars(cfg.full_warmup_bars + 10)
        result = pipeline.compute(df, "EURUSD", 100, 6, 2.0)
        assert isinstance(result, ModelFeatures)
        assert result.bar_ticks == 100.0
        assert result.horizon == 6.0
