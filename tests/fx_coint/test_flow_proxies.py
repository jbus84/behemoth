import numpy as np
import polars as pl

from scripts.fx_coint.flow_proxies import tick_rule_signs, quote_ofi, causal_zscore


def test_tick_rule_ffills_zero_diffs():
    mid = np.array([1.0, 1.1, 1.1, 1.0, 1.2])
    assert tick_rule_signs(mid).tolist() == [0.0, 1.0, 1.0, -1.0, 1.0]


def test_quote_ofi_sign_of_bid_minus_ask():
    bid = np.array([1.0, 1.1, 1.1, 1.0])
    ask = np.array([1.2, 1.2, 1.1, 1.1])
    assert quote_ofi(bid, ask).tolist() == [0.0, 1.0, 1.0, -1.0]


def test_causal_zscore_is_look_ahead_free():
    base = [0.0, 1.0, -1.0, 0.5, 2.0, -0.5, 1.5, 0.0, 1.0, -1.0, 0.3, 0.7]
    k = 6
    a = pl.Series(base)
    b = pl.Series(base[: k + 1] + [9.9, -9.9, 9.9, -9.9, 9.9])
    za = causal_zscore(a, span=4).to_numpy()
    zb = causal_zscore(b, span=4).to_numpy()
    np.testing.assert_allclose(za[: k + 1], zb[: k + 1], equal_nan=True)
