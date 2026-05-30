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
