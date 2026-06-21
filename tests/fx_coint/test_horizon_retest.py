# tests/fx_coint/test_horizon_retest.py
import numpy as np
import pandas as pd

from scripts.fx_coint.horizon_retest import build_horizon_panel


def _bars(n=400, start="2022-01-03 07:00"):
    # contiguous 1h bars within session, mid a gentle random walk
    idx = pd.date_range(start, periods=n, freq="1h")
    # keep only session hours 7..20 so build_freq_bars-style contig holds intraday
    rng = np.random.default_rng(0)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    df = pd.DataFrame({"bucket": idx, "mid": mid})
    df["contig"] = True
    df.loc[0, "contig"] = False
    return df


def test_forward_h_target_matches_h_bar_return():
    bars = _bars()
    p = build_horizon_panel(bars, H=3)
    # pick a row and verify ret_fwd_bps == 3-bar forward return at that bucket
    row = p.iloc[10]
    i = bars.index[bars["bucket"] == row["bucket"]][0]
    expect = (np.log(bars["mid"].iloc[i + 3]) - np.log(bars["mid"].iloc[i])) * 1e4
    assert np.isclose(row["ret_fwd_bps"], expect, atol=1e-6)
    assert "target_z" in p.columns and np.isfinite(p["target_z"]).all()


def test_non_contiguous_window_dropped():
    bars = _bars()
    bars.loc[20, "contig"] = False   # breaks any window spanning bar 20
    p = build_horizon_panel(bars, H=3)
    # buckets whose [i, i+3] window includes the broken bar 20 must be absent
    broken_buckets = set(bars["bucket"].iloc[17:20])
    assert not (broken_buckets & set(p["bucket"]))
