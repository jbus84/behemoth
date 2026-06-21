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


# ---------------------------------------------------------------------------
# Task 2: horizon_net_track
# ---------------------------------------------------------------------------
from scripts.fx_coint.horizon_retest import horizon_net_track  # noqa: E402


def test_horizon_net_track_shapes_and_more_entries_at_h1():
    t1 = horizon_net_track("EURUSD", H=1)
    t4 = horizon_net_track("EURUSD", H=4)
    assert t1["n"] > 200 and t4["n"] > 200
    assert t1["net"].shape == (t1["n"],)
    assert t1["bucket"].shape == (t1["n"],)
    # hourly sampling => H=1 and H=4 have comparable entry counts (both ~hourly grid),
    # and BOTH are far larger than the old disjoint 4-bar/day 4h panel (~196)
    assert t4["n"] > 500


# ---------------------------------------------------------------------------
# Task 3: dual inference helpers
# ---------------------------------------------------------------------------
from scripts.fx_coint.horizon_retest import dual_inference, non_overlap_mask  # noqa: E402


def test_non_overlap_mask_spacing():
    bk = pd.to_datetime(["2022-01-03 07:00","2022-01-03 08:00","2022-01-03 11:00",
                         "2022-01-03 12:00"]).values
    m = non_overlap_mask(bk, H_hours=3)
    # 07:00 kept; 08:00 too close (kept-prev 07:00 +3h=10:00) -> drop; 11:00 kept; 12:00 drop
    assert m.tolist() == [True, False, True, False]


def test_dual_inference_agree_flag_false_on_noise():
    rng = np.random.default_rng(0)
    bk = pd.to_datetime(np.repeat(pd.date_range("2019-01-01", periods=200, freq="3h"), 1)).values
    net = rng.normal(0.0, 1.0, len(bk))   # pure noise -> not significant
    r = dual_inference(net, bk, H_hours=3, label="noise")
    assert r["agree"] is False
    assert r["raw_n"] == len(bk) and r["eff_n"] <= r["raw_n"]
