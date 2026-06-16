import numpy as np

from scripts.fx_cluster.causal import causal_zscore, ewma_vol, rolling_minmax_pos


def test_ewma_vol_is_causal_and_positive():
    x = np.array([0.0, 0.01, -0.02, 0.03, -0.01])
    v = ewma_vol(x, lam=0.94)
    assert v.shape == x.shape
    assert v[0] == 0.0  # no history yet
    assert np.all(v[1:] > 0.0)
    # changing a FUTURE value must not change an earlier vol estimate (no look-ahead)
    x2 = x.copy()
    x2[-1] = 99.0
    v2 = ewma_vol(x2, lam=0.94)
    assert np.allclose(v[:-1], v2[:-1])


def test_causal_zscore_no_lookahead():
    x = np.arange(10, dtype=float)
    z = causal_zscore(x, window=4)
    x2 = x.copy()
    x2[7:] = -50.0
    z2 = causal_zscore(x2, window=4)
    assert np.allclose(z[:7], z2[:7], equal_nan=True)


def test_rolling_minmax_pos_bounds():
    x = np.array([1.0, 2.0, 3.0, 2.0, 1.0, 5.0])
    p = rolling_minmax_pos(x, window=3)
    assert np.nanmin(p) >= 0.0 and np.nanmax(p) <= 1.0
    # last point is the window max -> pos == 1.0 (window = {1,5} over [1,1,5])
    assert p[-1] == 1.0
