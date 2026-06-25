import numpy as np

from scripts.fx_coint.flow_metrics import (
    bh_fdr,
    deviation_tail_return,
    information_coefficient,
    ridge_oos,
    spearman_ic,
)


def test_ic_detects_strong_correlation():
    rng = np.random.default_rng(0)
    sig = rng.standard_normal(5000)
    fwd = 0.5 * sig + 0.1 * rng.standard_normal(5000)
    ic, t, n = information_coefficient(sig, fwd, horizon=1)
    assert ic > 0.7 and t > 10 and n == 5000


def test_ic_non_overlap_subsamples():
    sig = np.arange(100.0)
    _, _, n = information_coefficient(sig, sig, horizon=5)
    assert n == 20


def test_deviation_tail_follow_positive_when_signal_equals_fwd():
    rng = np.random.default_rng(1)
    sig = rng.standard_normal(2000)
    follow, fade = deviation_tail_return(sig, sig, q=0.90)
    assert follow > 0 and np.isclose(fade, -follow)


def test_bh_fdr_rejects_small_pvalues():
    p = np.array([0.001, 0.2, 0.04, 0.8, 0.0001])
    mask = bh_fdr(p, alpha=0.05)
    assert mask[0] and mask[4] and not mask[3]


def test_spearman_ic_monotonic():
    x = np.arange(200.0)
    y = x ** 2
    ic, t, n = spearman_ic(x, y)
    assert ic > 0.99 and n == 200


def test_ridge_oos_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X_is = rng.standard_normal((4000, 3))
    y_is = X_is[:, 0] * 0.8 + 0.1 * rng.standard_normal(4000)
    X_oos = rng.standard_normal((2000, 3))
    y_oos = X_oos[:, 0] * 0.8 + 0.1 * rng.standard_normal(2000)
    ic, r2, pred = ridge_oos(X_is, y_is, X_oos, y_oos, lam=10.0)
    assert ic > 0.9 and r2 > 0.7 and len(pred) == 2000


def test_ridge_oos_noise_gives_no_skill():
    rng = np.random.default_rng(1)
    X_is = rng.standard_normal((4000, 3))
    y_is = rng.standard_normal(4000)
    X_oos = rng.standard_normal((2000, 3))
    y_oos = rng.standard_normal(2000)
    ic, r2, _ = ridge_oos(X_is, y_is, X_oos, y_oos, lam=10.0)
    assert abs(ic) < 0.1 and r2 < 0.05
