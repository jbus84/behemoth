"""Per-cluster scoring with look-ahead-safe statistics.

block_bootstrap_pvalue: one-sided p that the mean > 0, resampling whole time-blocks
so correlated same-period trades are not treated as independent.
score_clusters: per cluster, pick the better side, compute mean net, persistence
metrics, and a bootstrap p-value. select_clusters: keep clusters whose mean net
beats the cost floor by margin, pass the persistence filter, then BH-FDR.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from scripts.fx_cluster import config


def block_bootstrap_pvalue(rets: np.ndarray, blocks: np.ndarray,
                           n_boot: int = config.BOOTSTRAP_BLOCKS, seed: int = config.RANDOM_SEED) -> float:
    """One-sided p-value for H0: mean(rets) <= 0, via block resampling of unique blocks."""
    rets = np.asarray(rets, dtype=float)
    uniq = np.unique(blocks)
    by_block = [rets[blocks == b] for b in uniq]
    rng = np.random.default_rng(seed)
    obs = rets.mean()
    centered = [g - obs for g in by_block]   # impose H0 mean 0
    count = 0
    nb = len(uniq)
    for _ in range(n_boot):
        pick = rng.integers(0, nb, nb)
        sample = np.concatenate([centered[k] for k in pick])
        if sample.mean() >= obs:
            count += 1
    return (count + 1) / (n_boot + 1)


def bh_fdr(pvals: np.ndarray, alpha: float = config.FDR_ALPHA) -> np.ndarray:
    """Benjamini-Hochberg: boolean reject mask."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    reject = np.zeros(m, dtype=bool)
    if passed.any():
        kmax = np.max(np.where(passed))
        reject[order[: kmax + 1]] = True
    return reject


def score_clusters(df: pl.DataFrame, cost_bps: float) -> list[dict]:
    """df columns: cluster, block, ret_long, ret_short, mfe, mae, hold_bars.
    cost is already inside ret_long/ret_short; cost_bps is kept for reporting."""
    out = []
    for cl in sorted(set(df["cluster"].to_list())):
        if cl == -1:
            continue
        sub = df.filter(pl.col("cluster") == cl)
        ml, ms = sub["ret_long"].mean(), sub["ret_short"].mean()
        side = 1 if ml >= ms else -1
        rets = (sub["ret_long"] if side == 1 else sub["ret_short"]).to_numpy()
        rets = rets[~np.isnan(rets)]
        blocks = sub["block"].to_numpy()[: len(rets)]
        mfe_mae = abs(sub["mfe"].mean() / sub["mae"].mean()) if sub["mae"].mean() != 0 else np.inf
        out.append({
            "cluster": cl, "side": side, "n": len(rets),
            "mean_net": float(np.mean(rets)) if len(rets) else float("nan"),
            "win_rate": float((rets > 0).mean()) if len(rets) else float("nan"),
            "pvalue": block_bootstrap_pvalue(rets, blocks) if len(rets) > 10 else 1.0,
            "mfe_mae": float(mfe_mae), "median_hold": float(sub["hold_bars"].median()),
            "cost_bps": cost_bps,
        })
    return out


def select_clusters(report: list[dict], margin_bps: float = config.SELECT_MARGIN_BPS) -> list[dict]:
    """Keep clusters that beat cost by margin, pass persistence, then BH-FDR."""
    cand = [r for r in report
            if r["mean_net"] > margin_bps
            and r["mfe_mae"] >= config.PERSIST_MIN_MFE_MAE
            and r["median_hold"] >= config.PERSIST_MIN_HOLD_BARS]
    if not cand:
        return []
    reject = bh_fdr(np.array([r["pvalue"] for r in cand]))
    return [r for r, keep in zip(cand, reject) if keep]
