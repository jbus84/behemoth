import numpy as np
import pandas as pd

from scripts.fx_coint.cointegration import (
    instrument_series, fit_hedge, residual, eg_test, half_life,
)


def _panel(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    # EURUSD random walk; GBPUSD = 0.8*EURUSD + stationary AR(1) noise -> cointegrated
    e = np.cumsum(rng.normal(0, 0.001, n)) + np.log(1.10)
    noise = np.zeros(n)
    for t in range(1, n):
        noise[t] = 0.9 * noise[t - 1] + rng.normal(0, 0.0005)
    g = 0.8 * e + noise + np.log(1.30) * 0.2
    cols = pd.MultiIndex.from_tuples([
        ("EURUSD", "logmid"), ("EURUSD", "spread"),
        ("GBPUSD", "logmid"), ("GBPUSD", "spread")])
    data = np.column_stack([e, np.full(n, 1e-4), g, np.full(n, 1e-4)])
    return pd.DataFrame(data, index=idx, columns=cols)


def test_instrument_series_combines_legs():
    p = _panel()
    s = instrument_series(p, "EURUSD")
    assert np.allclose(s.to_numpy(), p[("EURUSD", "logmid")].to_numpy())


def test_fit_hedge_recovers_beta():
    p = _panel()
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    assert 0.6 < beta < 1.0  # ~0.8


def test_eg_test_flags_cointegrated_pair():
    p = _panel()
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    res = residual(p, "GBPUSD", "EURUSD", beta)
    pval = eg_test(res)
    assert pval < 0.05


def test_eg_test_rejects_independent_walks():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2020-01-01", periods=2000, freq="1h", tz="UTC")
    a = np.cumsum(rng.normal(0, 0.001, 2000))
    b = np.cumsum(rng.normal(0, 0.001, 2000))
    cols = pd.MultiIndex.from_tuples([
        ("EURUSD", "logmid"), ("EURUSD", "spread"),
        ("GBPUSD", "logmid"), ("GBPUSD", "spread")])
    p = pd.DataFrame(np.column_stack([a, np.full(2000, 1e-4), b, np.full(2000, 1e-4)]),
                     index=idx, columns=cols)
    beta = fit_hedge(p, "GBPUSD", "EURUSD")
    pval = eg_test(residual(p, "GBPUSD", "EURUSD", beta))
    assert pval > 0.05


def test_half_life_positive_and_finite():
    p = _panel()
    res = residual(p, "GBPUSD", "EURUSD", fit_hedge(p, "GBPUSD", "EURUSD"))
    hl = half_life(res)
    assert 0 < hl < len(res)
