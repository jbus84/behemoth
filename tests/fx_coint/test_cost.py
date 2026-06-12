import numpy as np

from scripts.era_scalp.load_splits import _pip_size
from scripts.fx_coint.cost import MARKUP_SWEEP_PIPS, leg_cost_frac, spread_cost_frac


def test_markup_sweep_values():
    assert MARKUP_SWEEP_PIPS == (0.0, 0.3, 0.6, 1.0)


def test_leg_cost_frac_zero_markup_is_spread_over_mid():
    # EURUSD spread 0.0001 price, mid 1.10 -> ~9.09e-5 fractional
    c = leg_cost_frac("EURUSD", spread_price=1e-4, mid=1.10, markup_pips=0.0)
    assert np.isclose(c, 1e-4 / 1.10, rtol=1e-6)


def test_leg_cost_frac_adds_markup_in_price_units():
    # +0.6 pip on EURUSD = +0.6 * 1e-4 price
    c = leg_cost_frac("EURUSD", spread_price=1e-4, mid=1.10, markup_pips=0.6)
    assert np.isclose(c, (1e-4 + 0.6 * _pip_size("EURUSD")) / 1.10, rtol=1e-6)


def test_jpy_pip_size_used():
    c = leg_cost_frac("USDJPY", spread_price=0.01, mid=110.0, markup_pips=1.0)
    assert np.isclose(c, (0.01 + 1.0 * 0.01) / 110.0, rtol=1e-6)


def test_spread_cost_frac_sums_weighted_legs():
    # weight vector +1 EURUSD, -1 GBPUSD -> round-trip cost = |1|*cE + |1|*cG
    weights = np.zeros(6)
    weights[0] = 1.0
    weights[1] = -1.0
    spreads = np.full(6, 1e-4)
    mids = np.array([1.10, 1.30, 110.0, 0.90, 1.35, 0.65])
    total = spread_cost_frac(weights, spreads, mids, markup_pips=0.0)
    expected = 1e-4 / 1.10 + 1e-4 / 1.30
    assert np.isclose(total, expected, rtol=1e-6)
