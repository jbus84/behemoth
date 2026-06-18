import numpy as np
import pandas as pd
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile


def _synth(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    return pd.DataFrame({"bucket": pd.date_range("2024-01-01", periods=n, freq="h"), "mid": mid})


def test_horizon_label_balanced_and_horizon_correct():
    df = label_horizon_tercile(_synth(), horizon=3, window=500)
    v = df[df["_label_valid"]]
    fracs = v["tb_label"].value_counts(normalize=True)
    for c in (-1, 0, 1):
        assert abs(fracs[c] - 1 / 3) < 0.05            # balanced ~33%
    # fwd_ret_bps at i equals 3-bar forward mid return
    mid = df["mid"].to_numpy()
    i = 1000
    expected = (mid[i + 3] / mid[i] - 1) * 1e4
    assert abs(df["fwd_ret_bps"].iloc[i] - expected) < 1e-6
    # last `horizon` valid-eligible rows are invalid (no forward data)
    assert not df["_label_valid"].iloc[-1]
    assert not df["_label_valid"].iloc[-3]
