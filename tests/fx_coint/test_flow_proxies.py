import numpy as np
import polars as pl

from scripts.fx_coint.flow_proxies import tick_rule_signs, quote_ofi


def test_tick_rule_ffills_zero_diffs():
    mid = np.array([1.0, 1.1, 1.1, 1.0, 1.2])
    assert tick_rule_signs(mid).tolist() == [0.0, 1.0, 1.0, -1.0, 1.0]


def test_quote_ofi_sign_of_bid_minus_ask():
    bid = np.array([1.0, 1.1, 1.1, 1.0])
    ask = np.array([1.2, 1.2, 1.1, 1.1])
    assert quote_ofi(bid, ask).tolist() == [0.0, 1.0, 1.0, -1.0]
