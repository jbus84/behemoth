import numpy as np
import pandas as pd
import polars as pl

from scripts.fx_coint.phase0_scalp_common import (
    build_enriched_1m_bars,
    evaluate_family,
    is_near_miss,
)


def test_build_enriched_1m_bars_basic():
    rng = np.random.default_rng(42)
    n = 180  # 3 minutes of 1-second ticks
    timestamps = pd.date_range("2024-01-01 00:00:00", periods=n, freq="1s", tz="UTC")
    bid = 1.1000 + rng.normal(0, 0.00005, n).cumsum()
    ask = bid + 0.0003
    mid = (bid + ask) / 2
    ticks = pl.DataFrame({
        "timestamp": timestamps,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": 0.0003,
        "log_return": np.log(mid / np.roll(mid, 1)),
    })
    df = build_enriched_1m_bars(ticks, symbol="EURUSD")
    for col in ("bucket", "mid", "bid", "ask", "open_bid", "high_bid", "low_bid",
                "quote_revisions", "bar_return_sign"):
        assert col in df.columns
    assert len(df) == 3
    assert df["n_ticks"].sum() == 180


def test_evaluate_family_positive_signal():
    rng = np.random.default_rng(42)
    n = 1000
    signal = pd.Series(rng.choice([-1.0, 1.0], size=n))
    fwd_ret = signal * 0.001
    cost = 0.64 / 10_000
    result = evaluate_family(signal, fwd_ret, cost_frac=cost, entry_quantile=0.90)
    assert result["n_entries"] > 0
    assert result["gross_mean_bps"] > 0
    assert result["net_lb95_bps"] > 0
    assert result["verdict"] == "PASS"


def test_evaluate_family_random_noise():
    rng = np.random.default_rng(42)
    n = 5000
    signal = pd.Series(rng.normal(0, 1, n))
    fwd_ret = pd.Series(rng.normal(0, 0.0003, n))
    cost = 0.64 / 10_000
    result = evaluate_family(signal, fwd_ret, cost_frac=cost, entry_quantile=0.90)
    assert result["verdict"] in ("FAIL", "NEAR_MISS")


def test_is_near_miss_requires_below_cost_and_corroboration():
    cost = 0.64 / 10_000
    # just below cost + positive net mean -> near miss
    assert is_near_miss({"net_lb95_bps": -0.3, "net_mean_bps": 0.1}, cost)
    # deep negative -> not a near miss
    assert not is_near_miss({"net_lb95_bps": -5.0, "net_mean_bps": -3.0}, cost)
