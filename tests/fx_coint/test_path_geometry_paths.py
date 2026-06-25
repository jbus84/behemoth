import numpy as np
import pandas as pd

from scripts.fx_coint.path_geometry_paths import (
    hold_path,
    path_to_volnorm_returns,
)


def _synth():
    base = pd.Timestamp("2022-01-03 08:00")
    buckets = pd.date_range(base, periods=480, freq="1min").values
    mids = np.linspace(1.10, 1.12, 480)
    return buckets.astype("datetime64[ns]").astype("int64"), mids

def test_hold_path_one_bar_window():
    bn, mids = _synth()
    # 2h bar at 08:00 -> held next bar [10:00, 12:00) -> indices 120..239 (120 marks)
    path = hold_path(np.datetime64("2022-01-03 08:00"), "2h", bn, mids, n_bars=1)
    assert len(path) == 120
    assert np.isclose(path[0], mids[120])
    assert np.isclose(path[-1], mids[239])

def test_hold_path_two_bars_window():
    bn, mids = _synth()
    # n_bars=2 -> [10:00, 14:00) -> indices 120..359 (240 marks)
    path = hold_path(np.datetime64("2022-01-03 08:00"), "2h", bn, mids, n_bars=2)
    assert len(path) == 240
    assert np.isclose(path[0], mids[120])
    assert np.isclose(path[-1], mids[359])

def test_volnorm_guards():
    assert path_to_volnorm_returns(np.array([1.0]), 1.0).size == 0
    assert path_to_volnorm_returns(np.array([1.0, 1.1]), 0.0).size == 0
    out = path_to_volnorm_returns(np.array([1.0, 1.0001, 1.0002]), 1.0)
    assert out.shape == (2,) and np.all(out > 0)
