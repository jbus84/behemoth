"""Gross predictability metrics: non-overlap IC, deviation-tail conditional return,
Benjamini-Hochberg FDR. Pure numpy, no side effects."""

from __future__ import annotations

import numpy as np


def information_coefficient(signal: np.ndarray, fwd: np.ndarray, horizon: int) -> tuple[float, float, int]:
    """Pearson IC with NON-OVERLAPPING sampling (every `horizon` obs) for an honest
    t-stat. Returns (ic, tstat, n_used)."""
    s = signal[::horizon]
    f = fwd[::horizon]
    m = np.isfinite(s) & np.isfinite(f)
    s, f = s[m], f[m]
    if len(s) < 10:
        return (float("nan"), float("nan"), len(s))
    ic = float(np.corrcoef(s, f)[0, 1])
    t = ic * np.sqrt(len(s) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(s))


def deviation_tail_return(signal: np.ndarray, fwd: np.ndarray, q: float = 0.90) -> tuple[float, float]:
    """Mean forward return in the |signal| top-(1-q) tail. follow = mean(sign(signal)*fwd)
    (+ = continuation); fade = -follow. Same units as fwd."""
    a = np.abs(signal)
    m = np.isfinite(a) & np.isfinite(fwd) & np.isfinite(signal)
    a, sig, f = a[m], signal[m], fwd[m]
    if len(a) < 10:
        return (float("nan"), float("nan"))
    sel = a >= np.quantile(a, q)
    follow = float((np.sign(sig[sel]) * f[sel]).mean())
    return (follow, -follow)


def bh_fdr(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg. Returns a boolean rejection mask aligned with `pvals`."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    passed = ranked <= alpha * (np.arange(1, n + 1) / n)
    out = np.zeros(n, dtype=bool)
    if passed.any():
        k = int(np.where(passed)[0].max()) + 1
        out[order[:k]] = True
    return out


def spearman_ic(a: np.ndarray, b: np.ndarray) -> tuple[float, float, int]:
    """Rank IC over the finite intersection. Returns (ic, tstat, n)."""
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if len(a) < 10:
        return (float("nan"), float("nan"), len(a))
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ic = float(np.corrcoef(ra, rb)[0, 1])
    t = ic * np.sqrt(len(a) - 2) / np.sqrt(max(1e-12, 1.0 - ic**2))
    return (ic, float(t), len(a))


def ridge_oos(X_is: np.ndarray, y_is: np.ndarray, X_oos: np.ndarray, y_oos: np.ndarray,
              lam: float = 10.0) -> tuple[float, float, np.ndarray]:
    """Standardise on IS, fit ridge (intercept unpenalised), eval OOS.
    Returns (oos_ic, oos_r2, oos_pred). NaN rows are dropped per split."""
    fi = np.isfinite(X_is).all(1) & np.isfinite(y_is)
    fo = np.isfinite(X_oos).all(1) & np.isfinite(y_oos)
    Xi, yi, Xo, yo = X_is[fi], y_is[fi], X_oos[fo], y_oos[fo]
    mu, sd = Xi.mean(0), Xi.std(0) + 1e-9
    Xi = np.column_stack([np.ones(len(Xi)), (Xi - mu) / sd])
    Xo = np.column_stack([np.ones(len(Xo)), (Xo - mu) / sd])
    pen = np.eye(Xi.shape[1])
    pen[0, 0] = 0.0
    w = np.linalg.solve(Xi.T @ Xi + lam * pen, Xi.T @ yi)
    pred = Xo @ w
    ic = float(np.corrcoef(pred, yo)[0, 1]) if len(yo) > 2 else float("nan")
    ss_tot = float(((yo - yo.mean()) ** 2).sum())
    r2 = float(1.0 - ((yo - pred) ** 2).sum() / ss_tot) if ss_tot > 0 else float("nan")
    return (ic, r2, pred)
