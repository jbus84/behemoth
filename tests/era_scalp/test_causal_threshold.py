import numpy as np

from scripts.era_scalp.trade_harness import expanding_quantile_threshold


def test_threshold_is_nan_before_warmup():
    s = np.arange(1, 101, dtype=float)
    thr = expanding_quantile_threshold(s, q=0.9, warmup=20, recompute_every=1)
    assert np.all(np.isnan(thr[:19]))
    assert np.isfinite(thr[19])


def test_threshold_only_uses_past():
    rng = np.random.default_rng(0)
    s = rng.standard_normal(500)
    thr_a = expanding_quantile_threshold(s, q=0.95, warmup=50, recompute_every=10)
    s2 = s.copy()
    s2[300:] = rng.standard_normal(200) * 50.0
    thr_b = expanding_quantile_threshold(s2, q=0.95, warmup=50, recompute_every=10)
    finite = np.isfinite(thr_a[:300]) & np.isfinite(thr_b[:300])
    assert finite.any()
    assert np.allclose(thr_a[:300][finite[:300]], thr_b[:300][finite[:300]])


def test_threshold_handles_nan_signal():
    s = np.array([np.nan, 1.0, np.nan, 2.0, 3.0, 4.0, 5.0, 6.0])
    thr = expanding_quantile_threshold(s, q=0.5, warmup=3, recompute_every=1)
    assert np.isnan(thr[0]) and np.isnan(thr[1])
    assert np.isfinite(thr[4])
