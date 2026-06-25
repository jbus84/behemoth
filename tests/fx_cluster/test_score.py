import numpy as np
import polars as pl

from scripts.fx_cluster.score import (
    bh_fdr,
    block_bootstrap_pvalue,
    score_clusters,
    select_clusters,
)


def test_block_bootstrap_detects_real_positive_mean():
    rng = np.random.default_rng(0)
    blocks = rng.integers(0, 20, 2000)
    rets = rng.normal(0.5, 1.0, 2000)        # clearly positive mean
    p = block_bootstrap_pvalue(rets, blocks, n_boot=2000, seed=1)
    assert p < 0.05


def test_block_bootstrap_noise_not_significant():
    rng = np.random.default_rng(2)
    blocks = rng.integers(0, 20, 2000)
    rets = rng.normal(0.0, 1.0, 2000)
    p = block_bootstrap_pvalue(rets, blocks, n_boot=2000, seed=1)
    assert p > 0.05


def test_bh_fdr_rejects_small_pvalues():
    p = np.array([0.001, 0.02, 0.2, 0.8])
    rej = bh_fdr(p, alpha=0.10)
    assert rej[0] and not rej[3]


def test_score_and_select_picks_profitable_cluster():
    # cluster 0 = strong long edge; cluster 1 = noise; -1 = noise label (ignored).
    n = 1200
    rng = np.random.default_rng(3)
    labels = np.array([0] * 400 + [1] * 400 + [-1] * 400)
    df = pl.DataFrame({
        "cluster": labels,
        "block": rng.integers(0, 30, n),
        "ret_long": np.concatenate([rng.normal(1.0, 1.0, 400), rng.normal(0.0, 1.0, 400), rng.normal(0, 1, 400)]),
        "ret_short": np.concatenate([rng.normal(-1.0, 1.0, 400), rng.normal(0.0, 1.0, 400), rng.normal(0, 1, 400)]),
        "mfe": np.full(n, 5.0), "mae": np.full(n, -1.0), "hold_bars": np.full(n, 6),
    })
    report = score_clusters(df, cost_bps=0.7)
    sel = select_clusters(report, margin_bps=0.2)
    assert 0 in [r["cluster"] for r in sel]
    assert all(r["side"] == 1 for r in sel if r["cluster"] == 0)
    assert 1 not in [r["cluster"] for r in sel]
