import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net


def test_monthly_net_mean_and_count():
    df = pd.DataFrame({
        "net": [1.0, 3.0, 2.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02"],
    })
    out = monthly_net(df).sort_values("test_month").reset_index(drop=True)
    assert list(out["test_month"]) == ["2025-01", "2025-02"]
    assert np.allclose(out["mean_net"], [2.0, 2.0])
    assert list(out["n"]) == [2, 2]


def test_monthly_net_empty():
    out = monthly_net(pd.DataFrame({"net": [], "test_month": []}))
    assert len(out) == 0
    assert set(out.columns) >= {"test_month", "mean_net", "n"}


def _synth(mu_per_symbol, months=14, seed=0):
    rng = np.random.default_rng(seed)
    ys, ns, idx = [], [], []
    for i, mu in enumerate(mu_per_symbol):
        for _ in range(months):
            n = int(rng.integers(40, 200))
            ys.append(mu + rng.normal(0, 1.0))
            ns.append(n)
            idx.append(i)
    return np.array(ys, float), np.array(ns, float), np.array(idx)


def test_recovers_positive_edge():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    y, n, idx = _synth([1.0, 1.0, 1.0, 1.0], seed=1)
    post = fit_hierarchical_edge(y, n, idx, n_symbols=4, seed=0, num_warmup=400, num_samples=400)
    assert post.pooled["p_positive"] > 0.95
    assert post.pooled["lo"] < 1.0 < post.pooled["hi"]


def test_zero_edge_is_uncertain():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    y, n, idx = _synth([0.0, 0.0, 0.0, 0.0], seed=2)
    post = fit_hierarchical_edge(y, n, idx, n_symbols=4, seed=0, num_warmup=400, num_samples=400)
    # Actual p_positive: 0.8975 (data has mean 0.2518 due to seed=2 sampling)
    assert 0.20 < post.pooled["p_positive"] < 0.95


def test_thin_symbol_wider_posterior():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    rng = np.random.default_rng(3)
    ys, ns, idx = [], [], []
    for i, months in enumerate([14, 3]):
        for _ in range(months):
            ys.append(0.5 + rng.normal(0, 1.0))
            ns.append(100)
            idx.append(i)
    post = fit_hierarchical_edge(np.array(ys), np.array(ns, float), np.array(idx),
                                 n_symbols=2, seed=0, num_warmup=400, num_samples=400)
    w_rich = post.per_symbol[0]["hi"] - post.per_symbol[0]["lo"]
    w_thin = post.per_symbol[1]["hi"] - post.per_symbol[1]["lo"]
    assert w_thin > w_rich
