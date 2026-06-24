"""Two-track edge-based feature search (Stage 1 screen).

Replaces IC as the search objective with edge-leaning statistics, after this
project established that IC robustness != tradeable P&L. Per role:
  direction : |return|-weighted directional IC (emphasises big-money events)
  magnitude : IC of feature vs |return| (rank move size -> select cost-clearers)
  condition : tercile net-bps spread of the base fade P&L (interaction value)
Survivors are confirmed by marginal net-bps lift in pnl_walkforward (Stage 2).

No modelling: all combinations are simple non-fit rules.

Usage: uv run python scripts/fx_coint/edge_feature_search.py
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _finite_pair(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    return a[ok], b[ok]


def weighted_directional_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Weighted rank correlation of feat vs ret, weights ∝ |ret|.

    Uses weighted Pearson correlation of the rank-transformed series, so large
    moves (which dominate P&L) dominate the statistic. Returns 0.0 if degenerate.
    """
    f, r = _finite_pair(feat, ret)
    if f.size < 10:
        return 0.0
    w = np.abs(r)
    if w.sum() == 0:
        return 0.0
    fr = stats.rankdata(f)
    rr = stats.rankdata(r)

    def wmean(x):
        return np.sum(w * x) / np.sum(w)

    fm, rm = wmean(fr), wmean(rr)
    cov = wmean((fr - fm) * (rr - rm))
    vf = wmean((fr - fm) ** 2)
    vr = wmean((rr - rm) ** 2)
    den = np.sqrt(vf * vr)
    return float(cov / den) if den > 0 else 0.0


def magnitude_ic(feat: np.ndarray, ret: np.ndarray) -> float:
    """Spearman IC of feat vs |ret| — does the feature rank move size?"""
    f, r = _finite_pair(feat, ret)
    if f.size < 10 or np.unique(f).size < 3:
        return 0.0
    return float(stats.spearmanr(f, np.abs(r))[0])


if __name__ == "__main__":
    pass
