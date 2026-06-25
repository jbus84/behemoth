"""Multiplicity corrections for the flow-direction grid."""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def p_from_t(t: float, n: int) -> float:
    return float(2 * (1 - norm.cdf(abs(t))))


def sidak_alpha(alpha: float, m: int) -> float:
    return float(1 - (1 - alpha) ** (1 / m))


def bh_reject(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.where(passed)[0]
    out = np.zeros(m, dtype=bool)
    if len(k):
        cutoff = order[: k.max() + 1]
        out[cutoff] = True
    return [bool(x) for x in out]
