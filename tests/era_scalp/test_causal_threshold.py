import numpy as np

from scripts.era_scalp.trade_harness import expanding_quantile_threshold, evaluate_trades


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


def test_evaluate_trades_causal_flag_changes_entries():
    n = 5000
    rng = np.random.default_rng(1)
    signal = rng.standard_normal(n)
    mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-5
    cost = np.full(n, 0.0)
    tm = np.array(["2024-01"] * n)
    full = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.95, h=10)
    causal = evaluate_trades(
        signal, mid, cost, tm, pip=1e-4, q=0.95, h=10,
        causal_threshold=True, warmup=500, recompute_every=200,
    )
    assert len(causal) < len(full)
    assert len(causal) > 0


def test_evaluate_trades_default_is_unchanged():
    n = 100
    signal = np.concatenate([np.full(50, 2.0), np.full(50, 0.0)])
    mid = 1.0 + np.arange(n) * 1e-4
    cost = np.full(n, 0.4)
    tm = np.array(["2024-01"] * n)
    df = evaluate_trades(signal, mid, cost, tm, pip=1e-4, q=0.50, h=10)
    assert len(df) > 0 and df["net"].mean() > 0


from scripts.era_scalp.ab_causal_threshold import ab_edge_delta


def test_ab_edge_delta_reports_both_modes():
    n = 4000
    rng = np.random.default_rng(2)
    signal = rng.standard_normal(n)
    mid = 1.0 + np.cumsum(rng.standard_normal(n)) * 1e-5
    cost = np.full(n, 0.0)
    tm = np.array(["2024-%02d" % (1 + (i // 400) % 12) for i in range(n)])
    out = ab_edge_delta(signal, mid, cost, tm, pip=1e-4, q=0.95, h=10,
                        warmup=500, recompute_every=200)
    assert set(out) >= {"full_mean_net", "causal_mean_net", "full_n", "causal_n", "delta"}
    assert out["full_n"] >= out["causal_n"]
    assert np.isclose(out["delta"], out["full_mean_net"] - out["causal_mean_net"])
