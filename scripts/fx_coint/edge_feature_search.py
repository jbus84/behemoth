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


def tercile_netbps_spread(base_pnl: np.ndarray, gate: np.ndarray) -> dict:
    """Net-bps spread of base P&L across terciles of `gate`. Judged in net-bps
    (cost cancels in the spread), not IC — the project's central lesson."""
    p = np.asarray(base_pnl, dtype=float)
    g = np.asarray(gate, dtype=float)
    ok = np.isfinite(p) & np.isfinite(g)
    p, g = p[ok], g[ok]
    if p.size < 30:
        return {"unc": float("nan"), "t_means": [float("nan")] * 3,
                "best_lift": float("nan"), "best_tercile": -1}
    unc = float(p.mean())
    q1, q2 = np.quantile(g, [1 / 3, 2 / 3])
    # Guard: if gate has no variance, q1 and q2 will be equal, making terciles
    # degenerate (all NaNs). Return the sentinel value.
    if np.isclose(q1, q2):
        return {"unc": unc, "t_means": [float("nan")] * 3,
                "best_lift": float("nan"), "best_tercile": -1}
    masks = [g <= q1, (g > q1) & (g <= q2), g > q2]
    t_means = [float(p[m].mean()) if m.sum() > 10 else float("nan") for m in masks]
    lifts = [tm - unc for tm in t_means]
    best = int(np.nanargmax(lifts))
    return {"unc": unc, "t_means": t_means,
            "best_lift": float(lifts[best]), "best_tercile": best}


if __name__ == "__main__":
    pass
