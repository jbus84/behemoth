from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.mining_family import (
    DoubleTouchFamily,
    FAMILY_REGISTRY,
    MiningFamily,
    NoTouchFamily,
    OcoFirstTouchFamily,
    resolve_families,
)


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


def _make_test_frame(n: int = 1000) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = 1.0
    return pd.DataFrame({
        "close_bid": base + rng.random(n) * 0.001,
        "low_bid": base - rng.random(n) * 0.002,
        "high_ask": base + rng.random(n) * 0.002,
        "close_ask": base + 0.0002 + rng.random(n) * 0.001,
        "hl_first": rng.random(n) * 0.001,
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


def test_double_touch_no_false_edge_on_driftless_data():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["double_touch"]
    rng = np.random.default_rng(99)
    n = 1500
    pip = 0.0001
    # Driftless random walk — sweeps occur but carry no continuation edge.
    base = 1.20000 + np.cumsum(rng.normal(0, 0.3 * pip, n))
    frame = pd.DataFrame({
        "close_bid": base,
        "close_ask": base + 0.2 * pip,
        "low_bid": base - rng.uniform(0.1, 0.4, n) * pip,
        "high_ask": base + 0.2 * pip + rng.uniform(0.1, 0.4, n) * pip,
    })
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 15, "window_B": 15, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0, "driftless fixture should still produce sweeps"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=100,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    z = baseline["random_baseline_z"]
    assert np.isnan(z) or z < 2.0


def test_double_touch_detects_structure_on_post_sweep_continuation():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["double_touch"]
    n = 1500
    pip = 0.0001
    # First 1000 bars have a steady downtrend; last 500 are flat.  A regime
    # restricted to the trending region should score well above the random-
    # entry baseline because random draws sample decided sweeps from the
    # flat region too, diluting the control mean.
    drift = np.concatenate([
        1.30000 - 0.5 * pip * np.arange(1000),
        np.full(500, 1.30000 - 0.5 * pip * 1000),
    ])
    blip = np.where(np.arange(n) % 25 == 1, 5.0 * pip, 0.0)
    close = drift + blip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + 0.2 * pip,
        "low_bid": close - 0.3 * pip,
        "high_ask": close + 0.2 * pip + 0.3 * pip,
    })
    regime_mask = np.zeros(len(frame), dtype=bool)
    regime_mask[:1000] = True
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 3.0,
              "b_pips": 3.0, "window_A": 5, "window_B": 5, "horizon": 5}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0, "sweep frame should produce entries"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert baseline["random_baseline_z"] > 2.0


def test_pullback_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("pullback") == ["pullback"]
    fam = FAMILY_REGISTRY["pullback"]
    assert fam.name == "pullback"
    assert isinstance(fam, MiningFamily)


def test_pullback_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["pullback"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2"})
    dirs = sorted({g["impulse_dir"] for g in grid})
    assert dirs == ["down", "up"]
    # 2 impulse_dir x 2 m_pips x 3 r_frac x 2 window_I x 2 window_P x 2 horizons
    assert len(grid) == 2 * 2 * 3 * 2 * 2 * 2
    assert all(g["window_R"] == 10 for g in grid)
    meta = fam.candidate_metadata(
        "london",
        {"impulse_dir": "up", "m_pips": 3.0, "r_frac": 0.5,
         "window_I": 5, "window_P": 15, "window_R": 10, "horizon": 2},
    )
    assert meta["family"] == "pullback"
    assert meta["state_id"] == "pullback__london__up_M3_R0.5_wI5_wP15_wR10_h2"
    assert meta["ml_ready_target_type"] == "pullback"
    assert "impulse=up" in meta["regime_desc"]


def test_pullback_family_entry_and_gross():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_pullback_frame

    fam = FAMILY_REGISTRY["pullback"]
    frame = _build_pullback_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    assert len(gross) == len(entries)
    assert np.isfinite(gross).sum() > 0


def test_pullback_family_param_grid_rejects_nonpositive():
    import pytest

    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["pullback"]
    with pytest.raises(ValueError):
        fam.param_grid({"barrier_grid_pips": "0", "horizons": "1"})


def test_pullback_no_false_edge_on_driftless_data():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["pullback"]
    rng = np.random.default_rng(99)
    n = 2500
    pip = 0.0001
    # Driftless random walk — impulse/pullback/resumption setups occur but
    # carry no continuation edge.
    base = 1.20000 + np.cumsum(rng.normal(0, 0.3 * pip, n))
    frame = pd.DataFrame({
        "close_bid": base,
        "close_ask": base + 0.2 * pip,
        "low_bid": base - rng.uniform(0.1, 0.5, n) * pip,
        "high_ask": base + 0.2 * pip + rng.uniform(0.1, 0.5, n) * pip,
    })
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0, "driftless fixture should still produce setups"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=100,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    z = baseline["random_baseline_z"]
    assert np.isnan(z) or z < 2.0


def test_pullback_detects_structure_on_post_resumption_continuation():
    import numpy as np
    import pandas as pd

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["pullback"]
    pip = 0.0001
    # One 30-bar cycle: 10 flat bars, a 6-pip impulse held 3 bars, a pullback
    # down to +1 pip held 3 bars, a resumption back to +6 pip, then a hold.
    # Tiled across the frame so an impulse->pullback->resumption completes
    # once per cycle.
    cycle = np.array(
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
         6, 6, 6,
         1, 1, 1,
         6, 6, 6,
         6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
        dtype=float,
    )
    assert cycle.size == 30
    bump = np.tile(cycle, 60) * pip
    n = bump.size  # 1800
    # First 1200 bars: a 0.5 pip/bar uptrend supplies real post-resumption
    # continuation. Last 600 bars: flat — setups still complete on the bump
    # shape but carry no continuation, diluting the control mean.
    trend_len = 1200
    drift = np.concatenate([
        0.5 * pip * np.arange(trend_len),
        np.full(n - trend_len, 0.5 * pip * trend_len),
    ])
    close = 1.30000 + drift + bump
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + 0.2 * pip,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + 0.2 * pip + 0.1 * pip,
    })
    regime_mask = np.zeros(n, dtype=bool)
    regime_mask[:trend_len] = True
    params = {"symbol": "EURUSD", "impulse_dir": "up", "m_pips": 3.0,
              "r_frac": 0.5, "window_I": 15, "window_P": 15,
              "window_R": 10, "horizon": 5}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0, "trending region should produce setups"
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert baseline["random_baseline_z"] > 2.0


def test_no_touch_family_registered_and_resolves():
    from scripts.mining_family import (
        FAMILY_REGISTRY,
        MiningFamily,
        resolve_families,
    )

    assert resolve_families("no_touch") == ["no_touch"]
    fam = FAMILY_REGISTRY["no_touch"]
    assert fam.name == "no_touch"
    assert isinstance(fam, MiningFamily)


def test_no_touch_family_grid_and_metadata():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["no_touch"]
    grid = fam.param_grid({"barrier_grid_pips": "2,3", "horizons": "1,2,3"})
    # 2 barrier widths x 3 horizons; symmetric barriers -> no direction axis.
    assert len(grid) == 2 * 3
    assert sorted({g["barrier_pips"] for g in grid}) == [2.0, 3.0]
    assert sorted({g["horizon"] for g in grid}) == [1, 2, 3]
    meta = fam.candidate_metadata(
        "london", {"barrier_pips": 3.0, "horizon": 2}
    )
    assert meta["family"] == "no_touch"
    assert meta["state_id"] == "no_touch__london__K3_h2"
    assert meta["ml_ready_target_type"] == "no_touch"
    assert "K=3" in meta["regime_desc"]


def test_no_touch_family_grid_rejects_non_positive():
    from scripts.mining_family import FAMILY_REGISTRY

    fam = FAMILY_REGISTRY["no_touch"]
    with pytest.raises(ValueError, match="non-positive"):
        fam.param_grid({"barrier_grid_pips": "0,3", "horizons": "1"})

def test_no_touch_entry_indices_not_gated_on_decided():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_breakout_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_breakout_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    prep = fam._precompute(frame, "EURUSD", params)
    i0 = np.asarray(prep["i0"], dtype=np.int64)
    # Every barrier is touched on a breakout frame, yet entry_indices still
    # returns the full i0 universe — no_touch does not gate on `decided`.
    assert np.asarray(prep["decided"], dtype=bool).all()
    assert np.array_equal(entries, i0)


def test_no_touch_gross_is_plus_k_when_no_touch():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_range_bound_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_range_bound_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    # Range never touches a +/-3 pip barrier -> every candidate wins +K.
    assert np.allclose(gross, 3.0)


def test_no_touch_gross_is_negative_on_breakout():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from tests.test_tick_opportunity_mining import _build_breakout_frame

    fam = FAMILY_REGISTRY["no_touch"]
    frame = _build_breakout_frame()
    allmask = np.ones(len(frame), dtype=bool)
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 5}
    entries = fam.entry_indices(frame, allmask, params)
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    assert gross.size > 0
    # Up-breakout that keeps running -> the range-fade loses.
    assert np.mean(gross) < 0.0


def test_no_touch_no_false_edge_on_driftless_data():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["no_touch"]
    # A driftless random walk: no regime is structurally calmer than another,
    # so a no_touch bet must NOT clear the random-entry baseline.
    rng = np.random.default_rng(20260519)
    n = 4000
    pip = 0.0001
    steps = rng.normal(0.0, 0.6 * pip, size=n)
    close = 1.30000 + np.cumsum(steps)
    spread = 0.2 * pip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.2 * pip,
        "high_ask": close + spread + 0.2 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })
    # Scatter the regime across the frame rather than taking a contiguous
    # block. Overlapping h-bar horizons make adjacent bars' outcomes
    # correlated, so a contiguous block behaves like one correlated sample
    # and drifts multiple sigma from a control built on decorrelated random
    # draws. A scattered mask is decorrelated like the baseline draws, so a
    # truly driftless frame yields z ~ 0.
    regime_mask = rng.random(n) < 0.5
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 8}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert abs(baseline["random_baseline_z"]) < 2.0


def test_no_touch_detects_structure_on_range_bound_regime():
    import numpy as np

    from scripts.mining_family import FAMILY_REGISTRY
    from scripts.mining_random_baseline import random_entry_baseline

    fam = FAMILY_REGISTRY["no_touch"]
    # First 2000 bars are a tight range (no barrier ever touched -> +K wins);
    # last 2000 are a strong trend (barriers touched, breakouts run -> losses).
    # A regime restricted to the range should beat the random-entry baseline,
    # because random draws sample the trending half too, diluting the control.
    n = 4000
    pip = 0.0001
    saw = (np.arange(2000) % 4 - 1.5) * 0.4 * pip  # +/-0.6 pip, never touches
    calm = 1.30000 + saw
    trend = calm[-1] + 0.8 * pip * np.arange(1, 2001)
    close = np.concatenate([calm, trend])
    spread = 0.2 * pip
    frame = pd.DataFrame({
        "close_bid": close,
        "close_ask": close + spread,
        "low_bid": close - 0.1 * pip,
        "high_ask": close + spread + 0.1 * pip,
        "hl_first": np.zeros(n, dtype=float),
    })
    regime_mask = np.zeros(len(frame), dtype=bool)
    regime_mask[:2000] = True
    params = {"symbol": "EURUSD", "barrier_pips": 3.0, "horizon": 8}
    entries = fam.entry_indices(frame, regime_mask, params)
    assert len(entries) > 0
    gross = fam.measure_gross(frame, entries, params)
    gross = gross[np.isfinite(gross)]
    cand_ev = float(np.mean(gross))
    baseline = random_entry_baseline(
        fam, frame, params,
        n_entries=len(entries), n_draws=200,
        rng=np.random.default_rng(7),
        candidate_gross_ev=cand_ev,
    )
    assert baseline["random_baseline_z"] > 2.0


def test_frame_fingerprint_distinguishes_different_content_same_shape():
    from scripts.mining_family import _frame_fingerprint

    # Same shape and columns, DIFFERENT content -> must NOT collide.
    a = pd.DataFrame({"close_bid": [1.0, 2.0, 3.0], "low_bid": [0.0, 0.0, 0.0]})
    b = pd.DataFrame({"close_bid": [9.0, 9.0, 9.0], "low_bid": [0.0, 0.0, 0.0]})
    assert _frame_fingerprint(a) != _frame_fingerprint(b)


def test_frame_fingerprint_is_stable_for_equal_content():
    from scripts.mining_family import _frame_fingerprint

    # Two distinct objects with identical content -> same fingerprint.
    a = pd.DataFrame({"close_bid": [1.0, 2.0, 3.0]})
    b = pd.DataFrame({"close_bid": [1.0, 2.0, 3.0]})
    assert _frame_fingerprint(a) == _frame_fingerprint(b)


def test_frame_fingerprint_distinguishes_different_columns():
    from scripts.mining_family import _frame_fingerprint

    a = pd.DataFrame({"close_bid": [1.0, 2.0, 3.0]})
    b = pd.DataFrame({"low_bid": [1.0, 2.0, 3.0]})
    assert _frame_fingerprint(a) != _frame_fingerprint(b)


def test_oco_first_touch_precompute_cache_returns_same_object():
    family = OcoFirstTouchFamily()
    frame = _make_test_frame()
    params = {"symbol": "EURUSD", "horizon": 10, "barrier_pips": 5.0}
    result1 = family._precompute(frame, "EURUSD", params)
    result2 = family._precompute(frame, "EURUSD", params)
    assert result1 is result2
    for key in ["i0", "gross", "side", "both_touched_lookahead", "decided", "touch_step"]:
        assert key in result1
        assert np.array_equal(result1[key], result2[key])


def test_oco_first_touch_measure_gross_with_precomputed():
    family = OcoFirstTouchFamily()
    frame = _make_test_frame()
    params = {"symbol": "EURUSD", "horizon": 10, "barrier_pips": 5.0}
    family.clear_cache()
    without = family.measure_gross(frame, np.array([0, 50, 100]), params)
    family.clear_cache()
    precomputed = family._precompute(frame, "EURUSD", params)
    with_pre = family.measure_gross(frame, np.array([0, 50, 100]), params, precomputed=precomputed)
    assert np.allclose(without, with_pre, equal_nan=True)


def test_double_touch_measure_gross_with_precomputed():
    family = DoubleTouchFamily()
    frame = _make_test_frame()
    params = {"symbol": "EURUSD", "sweep_dir": "up", "a_pips": 5.0, "b_pips": 2.0, "window_A": 5, "window_B": 15, "horizon": 10}
    family.clear_cache()
    without = family.measure_gross(frame, np.array([0, 50, 100]), params)
    family.clear_cache()
    precomputed = family._precompute(frame, "EURUSD", params)
    with_pre = family.measure_gross(frame, np.array([0, 50, 100]), params, precomputed=precomputed)
    assert np.allclose(without, with_pre, equal_nan=True)


def test_no_touch_measure_gross_with_precomputed():
    family = NoTouchFamily()
    frame = _make_test_frame()
    params = {"symbol": "EURUSD", "horizon": 10, "barrier_pips": 5.0}
    family.clear_cache()
    without = family.measure_gross(frame, np.array([0, 50, 100]), params)
    family.clear_cache()
    precomputed = family._precompute(frame, "EURUSD", params)
    with_pre = family.measure_gross(frame, np.array([0, 50, 100]), params, precomputed=precomputed)
    assert np.allclose(without, with_pre, equal_nan=True)


def test_random_entry_baseline_parity_with_precompute():
    from scripts.mining_random_baseline import random_entry_baseline
    family = OcoFirstTouchFamily()
    frame = _make_test_frame()
    params = {"symbol": "EURUSD", "horizon": 10, "barrier_pips": 5.0}
    rng = np.random.default_rng(42)
    family.clear_cache()
    result_legacy = random_entry_baseline(
        family, frame, params,
        n_entries=5, n_draws=10, rng=rng,
        candidate_gross_ev=1.0,
    )
    family.clear_cache()
    rng = np.random.default_rng(42)
    precomputed = family._precompute(frame, "EURUSD", params)
    result_optimized = random_entry_baseline(
        family, frame, params,
        n_entries=5, n_draws=10, rng=rng,
        candidate_gross_ev=1.0,
        precomputed=precomputed,
    )
    assert np.isclose(result_legacy["random_baseline_z"], result_optimized["random_baseline_z"])
    assert np.isclose(result_legacy["random_baseline_p"], result_optimized["random_baseline_p"])
    assert np.isclose(result_legacy["random_baseline_control_mean"], result_optimized["random_baseline_control_mean"])
