from __future__ import annotations

import numpy as np

# A relationship must be stationary in at least this fraction of OOS windows.
MIN_STATIONARY_FRACTION = 0.6


def bh_fdr(pvals, alpha: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg: return keep-mask (True = reject null = stationary)."""
    p = np.asarray(pvals, float)
    n = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, n + 1) / n)
    passed = p[order] <= thresh
    keep = np.zeros(n, dtype=bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        keep[order[: kmax + 1]] = True
    return keep.tolist()


def fraction_stationary(oos_pvals, p_thresh: float = 0.05) -> float:
    p = np.asarray(oos_pvals, float)
    return float((p < p_thresh).mean()) if len(p) else 0.0


def structure_exists(wf: dict) -> bool:
    """Condition A (pre-FDR): stable across walk-forward windows."""
    return (wf["n_windows"] >= 3
            and wf["fraction_stationary"] >= MIN_STATIONARY_FRACTION)
