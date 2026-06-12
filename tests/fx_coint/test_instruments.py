import numpy as np
from scripts.fx_coint.instruments import (
    MAJORS, CURRENCIES, ccy_weight, instrument_weight, all_pairs,
)


def test_majors_and_currencies():
    assert MAJORS == ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"]
    assert set(CURRENCIES) == {"EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "USD"}


def test_ccy_weight_usd_quote_is_plus_one():
    w = ccy_weight("EUR")
    assert w[MAJORS.index("EURUSD")] == 1.0
    assert w.sum() == 1.0


def test_ccy_weight_usd_base_is_minus_one():
    w = ccy_weight("JPY")
    assert w[MAJORS.index("USDJPY")] == -1.0


def test_usd_is_zero_vector():
    assert np.allclose(ccy_weight("USD"), np.zeros(len(MAJORS)))


def test_real_pair_is_unit_vector():
    w = instrument_weight("EURUSD")
    expected = np.zeros(len(MAJORS)); expected[0] = 1.0
    assert np.allclose(w, expected)


def test_synthetic_cross_is_difference_of_legs():
    # EURGBP = logUSD[EUR] - logUSD[GBP] = +EURUSD - GBPUSD
    w = instrument_weight("EURGBP")
    assert w[MAJORS.index("EURUSD")] == 1.0
    assert w[MAJORS.index("GBPUSD")] == -1.0


def test_cross_with_usd_base_leg():
    # AUDJPY = +AUDUSD - (-USDJPY) = +AUDUSD + USDJPY
    w = instrument_weight("AUDJPY")
    assert w[MAJORS.index("AUDUSD")] == 1.0
    assert w[MAJORS.index("USDJPY")] == 1.0


def test_all_pairs_count():
    # 7 currencies choose 2 = 21 instruments (6 real USD majors + 15 crosses)
    assert len(all_pairs()) == 21
