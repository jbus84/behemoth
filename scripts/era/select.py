from __future__ import annotations

import numpy as np


def bh_fdr(pvalues: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.asarray(pvalues, float)
    ok = np.isfinite(p)
    idx = np.where(ok)[0]
    if idx.size == 0:
        return np.zeros_like(p, dtype=bool)
    order = idx[np.argsort(p[idx])]
    m = order.size
    thresh = 0.0
    for rank, i in enumerate(order, start=1):
        if p[i] <= rank / m * q:
            thresh = p[i]
    return ok & (p <= thresh)


def holdout_pvalue(net: np.ndarray) -> float:
    """One-sided p-value that mean(net) > 0 via a normal-approx t statistic.

    No scipy dependency: uses the standard-normal survival function via erf.
    Returns 1.0 (non-significant) when there are too few samples.
    """
    import math

    net = np.asarray(net, float)
    net = net[np.isfinite(net)]
    n = net.size
    if n < 5:
        return 1.0
    sd = net.std(ddof=1)
    if sd == 0:
        return 0.0 if net.mean() > 0 else 1.0
    t = net.mean() / (sd / math.sqrt(n))
    return float(0.5 * math.erfc(t / math.sqrt(2.0)))
