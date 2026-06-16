from datetime import datetime

import numpy as np
import polars as pl

from scripts.fx_coint.flow_proxies import bars_from_ticks, causal_zscore, quote_ofi, tick_rule_signs


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


def test_bars_from_ticks_aggregates_last_and_mean():
    ticks = pl.DataFrame(
        {
            "timestamp": [
                datetime(2020, 1, 1, 0, 0, 1),
                datetime(2020, 1, 1, 0, 0, 30),
                datetime(2020, 1, 1, 0, 1, 5),
                datetime(2020, 1, 1, 0, 1, 50),
            ],
            "bid": [1.0, 1.1, 1.1, 1.2],
            "ask": [1.2, 1.2, 1.3, 1.3],
            "mid": [1.10, 1.15, 1.20, 1.25],
        }
    )
    bars = bars_from_ticks(ticks, "1m")
    assert bars.height == 2
    assert bars.sort("bucket")["mid"].to_list()[-1] == 1.25
    assert {"bucket", "mid", "bid", "ask", "flow_tick", "flow_ofi", "n_ticks"} <= set(bars.columns)
