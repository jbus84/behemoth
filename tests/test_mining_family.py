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


def test_oco_family_registered_with_barrier_param_grid():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_first_touch"]
    assert fam.name == "oco_first_touch"
    grid = fam.param_grid({"barrier_grid_pips": "2,3,5", "horizons": "1,2"})
    barriers = sorted({g["barrier_pips"] for g in grid})
    horizons = sorted({g["horizon"] for g in grid})
    assert barriers == [2.0, 3.0, 5.0]
    assert horizons == [1, 2]
    meta = fam.candidate_metadata("london", {"barrier_pips": 5.0, "horizon": 2})
    assert meta["family"] == "oco_first_touch"
    assert meta["state_id"] == "oco_first_touch__london__k5"
    assert meta["ml_ready_target_type"] == "oco_expand"
    assert "barrier=5.0" in meta["regime_desc"]


def _oco_test_frame(n: int) -> pd.DataFrame:
    """Build a frame with the minimal columns _oco_precompute_candidates needs."""
    return pd.DataFrame({
        "close_ts": pd.date_range("2024-01-01", periods=n, freq="min"),
        "mid": np.arange(n, dtype=float),
        "spread": np.full(n, 0.5),
        "close_bid": np.arange(n, dtype=float),
        "high_bid": np.arange(n, dtype=float),
        "low_bid": np.arange(n, dtype=float),
        "high_ask": np.arange(n, dtype=float),
        "close_ask": np.arange(n, dtype=float),
        "hl_first": np.full(n, 1.0),
    })


def test_oco_family_entry_indices_basic():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_first_touch"]
    # Need > 102 bars so n_eff = len - 2*h > 100
    frame = _oco_test_frame(110)
    regime_mask = np.array([True] * 55 + [False] * 55)
    params = {"horizon": 1, "barrier_pips": 1.0, "symbol": "EURUSD"}
    entries = fam.entry_indices(frame, regime_mask, params)
    # Should only return entries from the regime_mask True region
    assert len(entries) > 0
    assert all(e < 55 for e in entries)


def test_oco_family_measure_gross_returns_nan_for_entries_outside_i0():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_first_touch"]
    frame = _oco_test_frame(110)
    params = {"horizon": 1, "barrier_pips": 1.0, "symbol": "EURUSD"}
    real_entries = fam.entry_indices(frame, np.full(110, True), params)
    assert len(real_entries) > 0
    gross = fam.measure_gross(frame, real_entries, params)
    assert len(gross) == len(real_entries)
    assert all(np.isfinite(gross))
    # n_eff = 108, so index 109 is outside i0
    bad_entries = np.array([real_entries[0], 109])
    gross_mixed = fam.measure_gross(frame, bad_entries, params)
    assert np.isfinite(gross_mixed[0])
    assert np.isnan(gross_mixed[1])


def test_oco_family_measure_gross_empty_when_no_precompute():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["oco_first_touch"]
    frame = pd.DataFrame({"mid": [1.0]})
    params = {"horizon": 1, "barrier_pips": 1.0, "symbol": "EURUSD"}
    entries = np.array([0])
    gross = fam.measure_gross(frame, entries, params)
    assert len(gross) == 0


def test_double_touch_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("double_touch") == ["double_touch"]
    fam = FAMILY_REGISTRY["double_touch"]
    assert fam.name == "double_touch"
    assert isinstance(fam, MiningFamily)


def test_double_touch_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["double_touch"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2"})
    sweeps = sorted({g["sweep_dir"] for g in grid})
    assert sweeps == ["down", "up"]
    # 2 sweep_dir x 2 a_pips x 2 b_pips x 2 window_A x 2 window_B x 2 horizons
    assert len(grid) == 2 * 2 * 2 * 2 * 2 * 2
    meta = fam.candidate_metadata(
        "london",
        {"sweep_dir": "up", "a_pips": 3.0, "b_pips": 2.0,
         "window_A": 5, "window_B": 15, "horizon": 2},
    )
    assert meta["family"] == "double_touch"
    assert meta["state_id"] == "double_touch__london__up_a3_b2_wA5_wB15_h2"
    assert meta["ml_ready_target_type"] == "double_touch"
    assert "sweep=up" in meta["regime_desc"]


def test_double_touch_family_entry_and_gross():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_sweep_frame

    fam = FAMILY_REGISTRY["double_touch"]
    frame = _build_sweep_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 5, "window_B": 5, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    assert len(gross) == len(entries)
    assert np.isfinite(gross).sum() > 0


def test_double_touch_family_param_grid_rejects_nonpositive():
    import pytest

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["double_touch"]
    with pytest.raises(ValueError):
        fam.param_grid({"barrier_grid_pips": "0", "horizons": "1"})
