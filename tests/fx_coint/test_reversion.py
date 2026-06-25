import numpy as np
import pandas as pd

from scripts.fx_coint.reversion import oos_reversion, ou_fit, reversion_exists


def _ou_series(n=3000, theta=0.05, sigma=0.001, seed=7):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = x[t - 1] - theta * x[t - 1] + rng.normal(0, sigma)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    return pd.Series(x, index=idx)


def test_ou_fit_recovers_positive_theta_and_halflife():
    s = _ou_series()
    fit = ou_fit(s)
    assert fit["theta"] > 0
    assert 0 < fit["half_life"] < 200


def test_oos_reversion_positive_for_mean_reverter():
    s = _ou_series()
    rev = oos_reversion(s, horizon=10)
    # on average, deviations shrink toward zero -> positive reversion fraction
    assert rev["mean_reversion_frac"] > 0
    assert rev["n_events"] > 100


def test_reversion_exists_true_for_ou():
    s = _ou_series()
    assert reversion_exists(ou_fit(s), oos_reversion(s, horizon=10))


def test_reversion_exists_false_for_random_walk():
    rng = np.random.default_rng(2)
    rw = pd.Series(np.cumsum(rng.normal(0, 0.001, 3000)))
    assert not reversion_exists(ou_fit(rw), oos_reversion(rw, horizon=10))
