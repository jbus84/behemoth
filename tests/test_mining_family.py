from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.mining_family import FAMILY_REGISTRY, MiningFamily, resolve_families


def test_resolve_families_maps_legacy_library_type():
    assert resolve_families("oco") == ["oco_first_touch"]
    assert resolve_families("directional") == ["directional"]
    assert resolve_families("separate") == ["oco_first_touch", "directional"]


def test_resolve_families_rejects_unknown():
    with pytest.raises(ValueError, match="unknown"):
        resolve_families("nonsense")


def test_registry_entries_satisfy_protocol():
    for name, fam in FAMILY_REGISTRY.items():
        assert isinstance(fam, MiningFamily)
        assert fam.name == name
        for method in ("param_grid", "entry_indices", "measure_gross",
                       "candidate_metadata"):
            assert callable(getattr(fam, method))


def test_directional_family_registered_and_measures_gross():
    fam = FAMILY_REGISTRY["directional"]
    assert fam.name == "directional"
    # measure_gross multiplies the per-bar side by the forward return.
    frame = pd.DataFrame({
        "y_fwd_pips_h1": [1.0, -2.0, 3.0, -4.0],
        "_dir_side_h1": np.array([1, 1, -1, -1], dtype=np.int8),
    })
    entries = np.array([0, 2, 3])
    gross = fam.measure_gross(frame, entries, {"horizon": 1})
    # side*y at indices 0,2,3 -> 1*1, -1*3, -1*-4
    assert list(gross) == [1.0, -3.0, 4.0]


def test_directional_family_entry_indices_missing_columns():
    fam = FAMILY_REGISTRY["directional"]
    frame = pd.DataFrame({"other": [1.0, 2.0, 3.0]})
    regime_mask = np.array([True, True, True])
    entries = fam.entry_indices(frame, regime_mask, {"horizon": 1})
    assert len(entries) == 0


def test_directional_family_entry_indices_excludes_last_h_bars():
    fam = FAMILY_REGISTRY["directional"]
    frame = pd.DataFrame({
        "y_fwd_pips_h2": [1.0, 2.0, 3.0, 4.0, 5.0],
        "_dir_side_h2": np.array([1, 1, 1, 1, 1], dtype=np.int8),
    })
    regime_mask = np.array([True, True, True, True, True])
    entries = fam.entry_indices(frame, regime_mask, {"horizon": 2})
    # Last 2 bars excluded, so only indices 0,1,2 are valid
    assert list(entries) == [0, 1, 2]


def test_directional_family_entry_indices_respects_regime_and_side():
    fam = FAMILY_REGISTRY["directional"]
    frame = pd.DataFrame({
        "y_fwd_pips_h1": [1.0, 2.0, 3.0, 4.0, 5.0],
        "_dir_side_h1": np.array([1, 0, -1, 1, -1], dtype=np.int8),
    })
    regime_mask = np.array([True, True, False, True, True])
    entries = fam.entry_indices(frame, regime_mask, {"horizon": 1})
    # Index 0: regime=True, side=1 -> included
    # Index 1: regime=True, side=0 -> excluded
    # Index 2: regime=False -> excluded
    # Index 3: regime=True, side=1 -> included
    # Index 4: last h bar -> excluded
    assert list(entries) == [0, 3]


def test_directional_family_param_grid():
    fam = FAMILY_REGISTRY["directional"]
    grid = fam.param_grid({"horizons": "1,3,5"})
    assert grid == [{"horizon": 1}, {"horizon": 3}, {"horizon": 5}]


def test_directional_family_candidate_metadata():
    fam = FAMILY_REGISTRY["directional"]
    meta = fam.candidate_metadata("london", {"horizon": 2})
    assert meta["family"] == "directional"
    assert meta["state_id"] == "directional__london__h2"
    assert meta["regime_desc"] == "london"
    assert meta["ml_ready_target_type"] == "directional"
