import numpy as np
import pandas as pd

from scripts.fx_coint.pf_paths import hold_path, path_to_volnorm_returns


def test_hold_path_selects_next_bar_window():
    base = pd.Timestamp("2022-01-03 08:00")
    buckets = pd.date_range(base, periods=240, freq="1min").values
    mids = np.linspace(1.10, 1.11, 240)
    buckets_ns = buckets.astype("datetime64[ns]").astype("int64")
    entry = np.datetime64("2022-01-03 08:00")  # 2h bar -> next window (08:00, 10:00]
    path = hold_path(entry, "2h", buckets_ns, mids)
    # hold_path selects (entry_bucket, entry_bucket+freq] = (08:00, 10:00]
    # On gapless 1-min synthetic data: 08:01..10:00 inclusive = 120 minute-marks (indices 1..120)
    assert len(path) == 120
    assert np.isclose(path[0], mids[1])  # first mid at 08:01
    assert np.isclose(path[-1], mids[120])  # last mid at 10:00


def test_path_to_volnorm_returns_scales_by_sigma():
    mids = np.array([1.0, 1.0001, 1.0002])
    out = path_to_volnorm_returns(mids, sigma_bps=1.0)
    assert out.shape == (2,)
    assert np.all(out > 0)


def test_path_to_volnorm_returns_guards():
    # Guard: len<2 should return empty
    out = path_to_volnorm_returns(np.array([1.0]), 1.0)
    assert len(out) == 0
    # Guard: sigma<=0 should return empty
    out = path_to_volnorm_returns(np.array([1.0, 1.1]), 0.0)
    assert len(out) == 0
