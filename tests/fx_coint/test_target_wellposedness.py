import numpy as np

from scripts.fx_coint.target_wellposedness import (
    class_balance,
    effective_n,
    regime_stability,
    temporal_concentration,
)


def test_effective_n_iid_series_has_tau_near_one():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(5000)
    out = effective_n(x)
    assert out["n"] == 5000
    assert 0.5 < out["tau"] < 2.0          # iid -> tau ~ 1
    assert out["n_eff"] > 2500              # close to n
    assert np.isclose(out["overlap_ratio"], out["n_eff"] / out["n"])


def test_effective_n_strongly_autocorrelated_series_collapses():
    # AR(1) phi=0.95 -> long memory -> tau >> 1, n_eff << n
    rng = np.random.default_rng(1)
    n = 5000
    x = np.zeros(n)
    eps = rng.standard_normal(n)
    for i in range(1, n):
        x[i] = 0.95 * x[i - 1] + eps[i]
    out = effective_n(x)
    assert out["tau"] > 5.0
    assert out["n_eff"] < n / 4


def test_temporal_concentration_uniform_vs_spiked():
    # 100 days, one value per day
    days = np.arange(100)
    uniform = np.ones(100)
    spiked = np.ones(100) * 0.01
    spiked[0] = 1000.0
    g_uniform = temporal_concentration(uniform, days)["gini"]
    g_spiked = temporal_concentration(spiked, days)
    assert g_uniform < 0.05                 # near-equal -> gini ~ 0
    assert g_spiked["gini"] > 0.9
    assert g_spiked["top1pct_share"] > 0.9  # ~all mass in 1 of 100 days


def test_class_balance_barrier_balanced_high_entropy():
    labels = np.array([1, -1, 0] * 100)
    out = class_balance(labels, kind="barrier")
    assert np.isclose(out["frac_up"], 1 / 3, atol=0.02)
    assert out["entropy"] > 0.95            # near-uniform 3 classes


def test_class_balance_barrier_degenerate_low_entropy():
    labels = np.array([1] * 297 + [-1, -1, 0])
    out = class_balance(labels, kind="barrier")
    assert out["frac_up"] > 0.95
    assert out["entropy"] < 0.2


def test_class_balance_continuous_reports_tail_share():
    x = np.concatenate([np.full(95, 0.01), np.full(5, 100.0)])
    out = class_balance(x, kind="continuous")
    assert out["tail_share"] > 0.9
    assert np.isnan(out["entropy"])


def test_regime_stability_stable_series_small_shift():
    rng = np.random.default_rng(2)
    x = rng.standard_normal(4000)
    out = regime_stability(x, split_idx=2000, kind="continuous")
    assert out["max_shift"] < 0.5


def test_regime_stability_vol_shift_detected():
    rng = np.random.default_rng(3)
    x = np.concatenate([rng.standard_normal(2000),
                        rng.standard_normal(2000) * 5.0])
    out = regime_stability(x, split_idx=2000, kind="continuous")
    assert out["vol_ratio"] > 3.0
    # max_shift uses |log(vol_ratio)| as the standardized vol shift, so a 5x
    # amplification yields |log(5)| ~= 1.61 (not the raw ratio). Brief's
    # placeholder >2.0 assumed raw-ratio max_shift; >1.5 is the correct
    # threshold for the log-vol semantics and still confirms detection.
    assert out["max_shift"] > 1.5


def test_label_noise_clear_barriers_low_flip():
    from scripts.fx_coint.target_wellposedness import label_noise
    # monotone strong uptrend -> up-touch is robust to a tiny barrier nudge
    logp = np.log(np.linspace(100, 110, 50))
    ev = np.array([0, 5, 10])
    vert = np.array([40, 45, 49])
    width = np.array([0.02, 0.02, 0.02])
    out = label_noise(logp, ev, vert, width, perturb=1e-5)
    assert out["flip_rate"] < 0.1


def test_label_noise_borderline_barriers_high_flip():
    from scripts.fx_coint.target_wellposedness import label_noise
    # down move (-0.6%) then a big up move (+1.5%): a narrow barrier touches DOWN
    # first (-1), but widening past the dip lets the UP move touch first (+1) -> flip.
    logp = np.log(np.array([100.0, 99.4, 101.5] + [101.5] * 20))
    ev = np.array([0])
    vert = np.array([20])
    w = np.log(100.0 / 99.4)  # ~0.6% half-width, sitting right on the dip
    width = np.array([w])
    out = label_noise(logp, ev, vert, width, perturb=w * 0.5)
    assert 0.0 <= out["flip_rate"] <= 1.0
    assert out["flip_rate"] > 0.0  # the single event flips dn -> up
    # widened scenario touches up, so the flip is attributed to frac_unstable_up
    assert out["frac_unstable_up"] > 0.0
    assert out["frac_unstable_up"] + out["frac_unstable_dn"] <= out["flip_rate"] + 1e-9


def test_label_noise_returns_valid_dict():
    from scripts.fx_coint.target_wellposedness import label_noise
    # verify return structure and bounds
    logp = np.log(np.array([100.0, 100.10, 99.92, 100.11, 99.90, 100.2] + [100.2] * 20))
    ev = np.array([0])
    vert = np.array([20])
    width = np.array([np.log(100.10 / 100.0)])
    out = label_noise(logp, ev, vert, width, perturb=np.log(100.10 / 100.0) * 0.5)
    assert isinstance(out, dict)
    assert "flip_rate" in out and "frac_unstable_up" in out and "frac_unstable_dn" in out
    assert 0.0 <= out["flip_rate"] <= 1.0
    assert 0.0 <= out["frac_unstable_up"] <= 1.0
    assert 0.0 <= out["frac_unstable_dn"] <= 1.0
    assert out["frac_unstable_up"] + out["frac_unstable_dn"] <= out["flip_rate"] + 1e-9
