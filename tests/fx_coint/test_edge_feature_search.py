import numpy as np
from scipy import stats

from scripts.fx_coint.edge_feature_search import magnitude_ic, weighted_directional_ic


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
