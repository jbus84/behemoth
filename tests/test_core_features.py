from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.behemoth.core.features import (
    CURRENT_FEATURE_SCHEMA,
    CURRENT_MODEL_FEATURE_CONTRACT,
    FeatureConfig,
    FeatureDefinition,
    ModelFeatureContract,
    compute_feature_matrix_from_bars,
)
from src.behemoth.core.schemas import ModelFeatures


def _make_bars(n_rows: int) -> pd.DataFrame:
    base_ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
    close = 1.1000 + np.cumsum(np.full(n_rows, 0.0001))
    high = close + 0.0002
    low = close - 0.0002
    open_ = close - 0.00005
    return pd.DataFrame(
        {
            "timestamp": [base_ts + timedelta(minutes=i) for i in range(n_rows)],
            "close_ts": [base_ts + timedelta(minutes=i, seconds=59) for i in range(n_rows)],
            "open_bid": open_,
            "high_bid": high,
            "low_bid": low,
            "close_bid": close,
            "spread": np.full(n_rows, 0.0002),
            "tick_volume": np.full(n_rows, 100.0),
            "hl_first": np.ones(n_rows),
            "hl_pos_frac": np.zeros(n_rows),
        }
    )


def test_compute_feature_matrix_keeps_prewarmup_rows_invalid() -> None:
    cfg = FeatureConfig()
    bars = _make_bars(cfg.full_warmup_bars + 11)

    matrix = compute_feature_matrix_from_bars(
        bars,
        symbol="EURUSD",
        bar_ticks=100,
        horizon=6,
        barrier_pips=2.0,
        cfg=cfg,
    )

    assert matrix is not None
    valid_mask = matrix.notna().all(axis=1)
    assert valid_mask.sum() == len(bars) - cfg.full_warmup_bars + 1
    assert valid_mask.idxmax() == cfg.full_warmup_bars - 1
    assert not valid_mask.iloc[cfg.full_warmup_bars - 2]


def test_current_feature_schema_matches_model_features_contract() -> None:
    assert CURRENT_FEATURE_SCHEMA.version == "oco_features_v1"
    assert CURRENT_FEATURE_SCHEMA.feature_names == tuple(ModelFeatures.model_fields)
    assert tuple(CURRENT_FEATURE_SCHEMA.feature_definitions) == CURRENT_FEATURE_SCHEMA.feature_names
    assert CURRENT_FEATURE_SCHEMA.rolling_windows == {
        "vol_window": 96,
        "cost_window": 288,
        "structural_window": 24,
    }


def test_feature_config_defaults_come_from_schema_manifest() -> None:
    cfg = FeatureConfig()

    assert cfg.schema_version == CURRENT_FEATURE_SCHEMA.version
    assert cfg.vol_window == CURRENT_FEATURE_SCHEMA.rolling_windows["vol_window"]
    assert cfg.cost_window == CURRENT_FEATURE_SCHEMA.rolling_windows["cost_window"]


def test_feature_schema_exposes_registry_metadata() -> None:
    definition = CURRENT_FEATURE_SCHEMA.definition_for("cost_est_pips")

    assert isinstance(definition, FeatureDefinition)
    assert definition.compute_group == "cost"
    assert definition.dependencies == ("spread", "range_pips")
    assert all(
        CURRENT_FEATURE_SCHEMA.definition_for(name).compute_group
        for name in CURRENT_FEATURE_SCHEMA.feature_names
    )


def test_model_feature_contract_enforces_schema_names() -> None:
    contract = ModelFeatureContract.from_schema(CURRENT_FEATURE_SCHEMA)

    assert contract == CURRENT_MODEL_FEATURE_CONTRACT
    assert contract.warmup_bars == ModelFeatures.WARMUP_BARS
    contract.validate_feature_names(tuple(ModelFeatures.model_fields))

    bad_names = tuple(ModelFeatures.model_fields)[:-1] + ("unexpected_feature",)
    with pytest.raises(ValueError, match="Feature Set contract mismatch"):
        contract.validate_feature_names(bad_names)
