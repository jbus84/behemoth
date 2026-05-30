"""Tests for run_tick_opportunity_monthly_wfo.py"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

try:
    from scripts.run_tick_opportunity_monthly_wfo import _build_registry_family_events
except ModuleNotFoundError:
    from run_tick_opportunity_monthly_wfo import _build_registry_family_events  # type: ignore


def test_build_registry_family_events_sets_underscore_context_keys():
    """Guard that cross-sectional families receive _dataset_dir and _horizons.

    Cross-sectional families (dollar_residual, dispersion_rank, lead_lag) read
    the dataset dir and horizons under underscore-prefixed keys in params
    (mining_family.py lines ~1030, ~1300, ~1528). Without these keys, the
    cross-symbol frame loader returns None and entry_indices returns zero
    entries, silently hiding all three families from evaluation.

    This test verifies that _build_registry_family_events sets both:
      params["_dataset_dir"] = str(dataset_dir)
      params["_horizons"] = horizons
    so that the families can locate their data.
    """
    # Build a minimal synthetic dataframe with close_ts and dummy features
    df = pd.DataFrame({
        "close_ts": pd.date_range("2024-01-01", periods=100, freq="h", tz="UTC"),
        "cost_est_pips": np.random.rand(100),
        "range_pips": np.random.rand(100),
        "ret1_pips": np.random.rand(100),
        "ret_z": np.random.rand(100),
        "ret_abs_z": np.random.rand(100),
    })

    # Build a minimal candidate row for lead_lag family
    cands = pd.DataFrame({
        "family": ["lead_lag"],
        "symbol": ["EURUSD"],
        "bar_ticks": [1000],
        "horizon": [1],
        "state_id": ["lead_lag__all__pGBPUSD_k1_z1.5"],
        "regime_desc": ["all;peer=GBPUSD;lag=1;z=1.5"],
        "quality_tier": ["high"],
        "quality_score": [95],
        "annualized_test_fills": [10.5],
        "mean_gross_pips_test": [0.25],
    })

    # Capture the params dict passed to entry_indices
    captured_params: list[dict[str, Any]] = []

    def mock_entry_indices(
        frame: pd.DataFrame, mask: np.ndarray, params: dict[str, Any]
    ) -> np.ndarray:
        """Mock entry_indices that captures params and returns empty array."""
        captured_params.append(params.copy())
        return np.array([], dtype=np.int64)

    # Monkeypatch the lead_lag family's entry_indices method
    try:
        from scripts.mining_family import FAMILY_REGISTRY
    except ModuleNotFoundError:
        from mining_family import FAMILY_REGISTRY  # type: ignore

    original_lead_lag = FAMILY_REGISTRY["lead_lag"]
    mock_family = MagicMock()
    mock_family.entry_indices = mock_entry_indices
    FAMILY_REGISTRY["lead_lag"] = mock_family

    try:
        # Call _build_registry_family_events with the test data
        _build_registry_family_events(
            split_name="train",
            df=df,
            q_fit={},
            cands=cands,
            max_events_per_candidate=100,
            bar_ticks=1000,
            dataset_dir=Path("/some/test/dir"),
            horizons=[1, 3, 6],
        )

        # Verify that entry_indices was called with the underscore keys
        assert len(captured_params) == 1, "entry_indices should have been called once"
        params = captured_params[0]

        # Assert the underscore-prefixed keys are present and correct
        assert "_dataset_dir" in params, "params must contain _dataset_dir"
        assert "_horizons" in params, "params must contain _horizons"
        assert params["_dataset_dir"] == "/some/test/dir"
        assert params["_horizons"] == [1, 3, 6]

        # Also verify the non-underscore keys are still present (backward compat)
        assert "dataset_dir" in params
        assert "horizons" in params
        assert params["dataset_dir"] == "/some/test/dir"
        assert params["horizons"] == [1, 3, 6]

    finally:
        # Restore the original family
        FAMILY_REGISTRY["lead_lag"] = original_lead_lag
