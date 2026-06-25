import numpy as np

from scripts.fx_cluster.factor import dollar_factor, oriented_returns, residuals


def test_oriented_returns_sign_convention():
    # EURUSD up by 1% => USD weaker => oriented (USD-strength) return negative.
    logret = {"EURUSD": np.array([0.01]), "USDJPY": np.array([0.01])}
    o = oriented_returns(logret)
    assert o["EURUSD"][0] < 0       # -1 sign
    assert o["USDJPY"][0] > 0       # +1 sign


def test_dollar_factor_is_equal_weighted_mean():
    o = {"A": np.array([0.02]), "B": np.array([0.04]), "C": np.array([-0.06])}
    f = dollar_factor(o)
    assert np.isclose(f[0], (0.02 + 0.04 - 0.06) / 3)


def test_residual_removes_common_factor():
    o = {"A": np.array([0.02]), "B": np.array([0.04]), "C": np.array([-0.06])}
    res = residuals(o)
    f = dollar_factor(o)
    assert np.isclose(res["A"][0], o["A"][0] - f[0])
    # residuals sum to ~0 across the cross-section (factor is the mean)
    assert np.isclose(sum(r[0] for r in res.values()), 0.0)
