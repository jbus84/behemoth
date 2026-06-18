import numpy as np
import pandas as pd
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile
from scripts.fx_coint.hourly_flow_features import add_channels, ARMS, build_panel
from scripts.fx_coint.multiplicity import p_from_t, sidak_alpha, bh_reject


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


def _synth_flow(n=2000, seed=1):
    rng = np.random.default_rng(seed)
    mid = 1.10 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    spread = np.abs(rng.normal(3e-5, 1e-5, n))
    return pd.DataFrame({
        "bucket": pd.date_range("2024-01-01", periods=n, freq="h"),
        "mid": mid, "bid": mid - spread / 2, "ask": mid + spread / 2,
        "n_ticks": rng.integers(50, 500, n).astype(float),
        "flow_tick": rng.normal(0, 0.03, n), "flow_ofi": rng.normal(0, 0.02, n),
        "rvol_bps": np.abs(rng.normal(1.0, 0.5, n)), "spread_bps": spread / mid * 1e4,
    })


def test_flow_channels_are_causal():
    df = _synth_flow()
    a = add_channels(df.copy())
    df2 = df.copy()
    df2.loc[df2.index[-5:], ["mid", "flow_ofi", "flow_tick"]] *= 1.5  # perturb the FUTURE
    b = add_channels(df2)
    # early-row channels must be unchanged by future perturbation (no leakage)
    cols = [c for c in ARMS["both"]]
    i = 1000
    for c in cols:
        assert abs(a[c].iloc[i] - b[c].iloc[i]) < 1e-9, f"channel {c} leaks future"


def test_build_panel_shapes():
    df = add_channels(_synth_flow())
    df["tb_label"] = np.resize([-1, 0, 1], len(df)).astype(np.int8)
    X, y, pos = build_panel(df, ARMS["both"], lookback=24)
    assert X.dtype == np.float64 and X.ndim == 3
    assert X.shape[1] == len(ARMS["both"]) and X.shape[2] == 24
    assert len(y) == X.shape[0] == len(pos)


def test_multiplicity_helpers():
    assert abs(p_from_t(0.0, 100) - 1.0) < 1e-9
    assert p_from_t(1.96, 100) < 0.06 and p_from_t(1.96, 100) > 0.04
    assert sidak_alpha(0.05, 12) < 0.05
    # BH: one tiny p among 12 should reject; all-large should not
    assert bh_reject([0.0001] + [0.9] * 11)[0] is True
    assert bh_reject([0.9] * 12) == [False] * 12
