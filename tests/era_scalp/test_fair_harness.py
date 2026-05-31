import numpy as np

from scripts.era_scalp.fair_harness import (
    fair_diagnostics,
    fair_node_score,
    forward_dev,
    ic_pvalue,
    info_coefficient,
)


def test_forward_dev_matches_naive():
    rng = np.random.default_rng(0)
    mid = 1.1 + np.cumsum(rng.standard_normal(200)) * 1e-4
    W, pip = 10, 1e-4
    fd = forward_dev(mid, pip, W)
    ref = np.full(len(mid), np.nan)
    for t in range(len(mid)):
        if t + W <= len(mid) - 1:
            ref[t] = (mid[t + 1:t + 1 + W].mean() - mid[t]) / pip
    fin = np.isfinite(ref)
    assert np.allclose(fd[fin], ref[fin], atol=1e-9)
    assert not np.isfinite(fd[-1])


def test_info_coefficient_perfect_and_random():
    rng = np.random.default_rng(1)
    realized = rng.standard_normal(500)
    ic_perfect, n = info_coefficient(realized.copy(), realized)
    assert ic_perfect > 0.99 and n == 500
    ic_rand, _ = info_coefficient(rng.standard_normal(500), realized)
    assert abs(ic_rand) < 0.2


def test_node_score_sign_agnostic():
    rng = np.random.default_rng(2)
    mid = 1.1 + np.cumsum(rng.standard_normal(800)) * 1e-4
    pip = 1e-4
    rd = forward_dev(mid, pip, 20)
    pred = np.where(np.isfinite(rd), rd, 0.0)
    s_pos = fair_node_score(pred, mid, pip, [20, 60])
    s_neg = fair_node_score(-pred, mid, pip, [20, 60])
    assert s_pos > 0 and abs(s_pos - s_neg) < 1e-6


def test_ic_pvalue():
    assert ic_pvalue(0.0, 1000) > 0.5
    assert ic_pvalue(0.3, 1000) < 0.01
    assert ic_pvalue(0.9, 10) == 1.0


def test_fair_diagnostics_keys():
    rng = np.random.default_rng(3)
    mid = 1.1 + np.cumsum(rng.standard_normal(400)) * 1e-4
    rd = forward_dev(mid, 1e-4, 20)
    pred = np.where(np.isfinite(rd), rd, 0.0)
    tm = np.array(["2025-01"] * 200 + ["2025-02"] * 200)
    d = fair_diagnostics(pred, mid, 1e-4, tm, 20)
    assert set(d) >= {"ic", "n_eff", "ic_by_month_consistency", "mean_abs_pred_pips",
                      "dev_sign_hitrate"}
    assert d["ic"] > 0.9
