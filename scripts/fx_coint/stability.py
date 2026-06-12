from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.fx_coint.cointegration import eg_test, fit_hedge, half_life, residual
from scripts.fx_coint.panels import walk_forward_windows

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


def walk_forward_eg(panel: pd.DataFrame, base: str, hedge: str,
                    train_years: int = 2):
    """Re-fit beta on each train window, test ADF on each OOS residual.

    Returns dict with oos p-values, per-window half-lives, and the mean OOS beta.
    Look-ahead safe: beta from train only, residual computed forward on OOS.
    """
    wins = walk_forward_windows(panel, train_years=train_years)
    oos_pvals, hls, betas = [], [], []
    for train, oos in wins:
        beta = fit_hedge(train, base, hedge)
        res_oos = residual(oos, base, hedge, beta)
        if len(res_oos) < 30:
            continue
        oos_pvals.append(eg_test(res_oos))
        hls.append(half_life(res_oos))
        betas.append(beta)
    return {
        "oos_pvals": oos_pvals,
        "half_lives": hls,
        "beta_mean": float(np.mean(betas)) if betas else float("nan"),
        "fraction_stationary": fraction_stationary(oos_pvals),
        "n_windows": len(oos_pvals),
    }


def structure_exists(wf: dict) -> bool:
    """Condition A (pre-FDR): stable across walk-forward windows."""
    return (wf["n_windows"] >= 3
            and wf["fraction_stationary"] >= MIN_STATIONARY_FRACTION)
