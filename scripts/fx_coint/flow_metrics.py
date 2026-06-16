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
