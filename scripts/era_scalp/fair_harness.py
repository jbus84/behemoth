from __future__ import annotations

import math

import numpy as np
import pandas as pd

# forward-window grid (bars) for the de-noised target y_fair
W_GRID = [20, 60, 200]
_MIN_PTS = 30


def forward_dev(mid: np.ndarray, pip: float, W: int) -> np.ndarray:
    """realized_dev[t] = (mean(mid[t+1..t+W]) - mid[t]) / pip; NaN where no full window."""
    mid = np.asarray(mid, float)
    n = mid.shape[0]
    out = np.full(n, np.nan)
    if n <= W:
        return out
    cm = np.concatenate(([0.0], np.cumsum(mid)))  # cm[i] = sum(mid[:i])
    t = np.arange(n)
    valid = t + W <= n - 1
    tv = t[valid]
    yfair = (cm[tv + W + 1] - cm[tv + 1]) / W
    out[tv] = (yfair - mid[tv]) / pip
    return out


def info_coefficient(pred: np.ndarray, realized: np.ndarray) -> tuple[float, int]:
    p = np.asarray(pred, float)
    r = np.asarray(realized, float)
    m = np.isfinite(p) & np.isfinite(r)
    n = int(m.sum())
    if n < _MIN_PTS:
        return float("nan"), n
    pp, rr = p[m], r[m]
    if pp.std() == 0 or rr.std() == 0:
        return float("nan"), n
    return float(np.corrcoef(pp, rr)[0, 1]), n


def fair_node_score(pred: np.ndarray, mid: np.ndarray, pip: float, w_grid=None) -> float:
    """Continuous, sign-agnostic per-node signal: best |IC|*sqrt(n_eff) over the W grid."""
    w_grid = w_grid or W_GRID
    best = 0.0
    for W in w_grid:
        ic, n = info_coefficient(pred, forward_dev(mid, pip, W))
        if np.isfinite(ic):
            best = max(best, abs(ic) * math.sqrt(n))
    return float(best)


def ic_pvalue(ic: float, n: int) -> float:
    """Two-sided p-value for a correlation via the normal approx (no scipy)."""
    if n < _MIN_PTS or not np.isfinite(ic) or abs(ic) >= 1.0:
        return 1.0
    t = ic * math.sqrt(n - 2) / math.sqrt(1.0 - ic * ic)
    return float(math.erfc(abs(t) / math.sqrt(2.0)))


def fair_diagnostics(pred, mid, pip, test_month, W) -> dict:
    rd = forward_dev(mid, pip, W)
    p = np.asarray(pred, float)
    m = np.isfinite(p) & np.isfinite(rd)
    n = int(m.sum())
    if n < _MIN_PTS:
        return {"ic": float("nan"), "n_eff": n, "ic_by_month_consistency": float("nan"),
                "mean_abs_pred_pips": float("nan"), "dev_sign_hitrate": float("nan")}
    ic, _ = info_coefficient(p, rd)
    pp, rr = p[m], rd[m]
    months = np.asarray(test_month)[m]
    by = pd.DataFrame({"p": pp, "r": rr, "mo": months}).groupby("mo")
    mics = by.apply(lambda g: float(np.corrcoef(g["p"], g["r"])[0, 1])
                    if len(g) >= _MIN_PTS and g["p"].std() and g["r"].std() else np.nan)
    mics = mics.dropna()
    consist = float((np.sign(mics) == np.sign(ic)).mean()) if len(mics) else float("nan")
    return {
        "ic": float(ic),
        "n_eff": n,
        "ic_by_month_consistency": consist,
        "mean_abs_pred_pips": float(np.mean(np.abs(pp))),
        "dev_sign_hitrate": float((np.sign(pp) == np.sign(rr)).mean()),
    }
