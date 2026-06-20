import numpy as np
import pandas as pd

from scripts.fx_coint.pf_paths import hold_path, path_to_volnorm_returns


def test_hold_path_selects_next_bar_window():
    base = pd.Timestamp("2022-01-03 08:00")
    buckets = pd.date_range(base, periods=240, freq="1min").values
    mids = np.linspace(1.10, 1.11, 240)
    buckets_ns = buckets.astype("datetime64[ns]").astype("int64")
    entry = np.datetime64("2022-01-03 08:00")  # 2h bar -> next window 10:00..12:00
    path = hold_path(entry, "2h", buckets_ns, mids)
    # next window is (10:00, 12:00] => 120 one-minute marks
    assert 110 <= len(path) <= 121
    assert path[0] > mids[0]


def test_path_to_volnorm_returns_scales_by_sigma():
    mids = np.array([1.0, 1.0001, 1.0002])
    out = path_to_volnorm_returns(mids, sigma_bps=1.0)
    assert out.shape == (2,)
    assert np.all(out > 0)
