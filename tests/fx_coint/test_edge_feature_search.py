import numpy as np
from scipy import stats

from scripts.fx_coint.edge_feature_search import (
    magnitude_ic,
    tercile_netbps_spread,
    weighted_directional_ic,
)


def test_weighted_directional_ic_emphasises_big_moves():
    rng = np.random.default_rng(0)
    n = 4000
    ret = rng.standard_normal(n)
    big = np.abs(ret) > 1.0
    # feature agrees with return sign on BIG moves, disagrees on small ones
    feat = np.where(big, np.sign(ret), -np.sign(ret)) + 0.1 * rng.standard_normal(n)
    wic = weighted_directional_ic(feat, ret)
    plain = stats.spearmanr(feat, ret)[0]
    assert wic > 0.2                 # big-move-weighted -> clearly positive
    assert wic > plain               # weighting beats the unweighted view


def test_weighted_directional_ic_nan_safe():
    feat = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
    ret = np.array([0.5, np.nan, 3.0, -1.0, 2.0])
    assert np.isfinite(weighted_directional_ic(feat, ret))


def test_magnitude_ic_detects_size_then_noise():
    rng = np.random.default_rng(1)
    ret = rng.standard_normal(3000)
    feat = np.abs(ret) + 0.1 * rng.standard_normal(3000)
    assert magnitude_ic(feat, ret) > 0.5
    noise = rng.standard_normal(3000)
    assert abs(magnitude_ic(noise, ret)) < 0.1


def test_tercile_netbps_spread_finds_conditioning():
    rng = np.random.default_rng(2)
    n = 6000
    gate = rng.standard_normal(n)
    base_pnl = 2.0 * gate + rng.standard_normal(n)     # high gate -> high P&L
    out = tercile_netbps_spread(base_pnl, gate)
    assert out["best_tercile"] == 2                    # top gate tercile is best
    assert out["best_lift"] > 0.5
    assert len(out["t_means"]) == 3


def test_tercile_netbps_spread_null_gate_small_lift():
    rng = np.random.default_rng(3)
    n = 6000
    base_pnl = rng.standard_normal(n)
    gate = rng.standard_normal(n)                      # independent of P&L
    out = tercile_netbps_spread(base_pnl, gate)
    assert out["best_lift"] < 0.15


def test_tercile_netbps_spread_constant_gate_no_crash():
    """Constant gate (no variance) should return sentinel, not crash."""
    rng = np.random.default_rng(4)
    n = 100
    base_pnl = rng.standard_normal(n)
    gate = np.ones(n)  # constant gate
    out = tercile_netbps_spread(base_pnl, gate)
    assert out["best_tercile"] == -1
    assert np.isnan(out["best_lift"])


from scripts.fx_coint.edge_feature_search import base_fade_pnl  # noqa: E402


def test_base_fade_pnl_matches_first_touch_return():
    # monotone uptrend: first-touch return from entry is positive
    logp = np.log(np.linspace(100, 110, 80))
    vol = np.full(80, 0.001)
    ev = np.array([0, 10, 20])
    ret = base_fade_pnl(logp, vol, ev, n_tb=30)
    assert ret.shape == (3,)
    assert np.all(ret > 0)             # uptrend -> positive forward move in bps
