from __future__ import annotations
import numpy as np, pandas as pd

def standardise(resid: np.ndarray) -> np.ndarray:
    r = np.asarray(resid, dtype=float)
    finite = np.isfinite(r)
    if finite.sum() < 2:
        return np.full_like(r, np.nan)
    mu = r[finite].mean(); sd = r[finite].std(ddof=0)
    if sd == 0:
        return np.zeros_like(r)
    return (r - mu) / sd

def evaluate_residual(residual, usd_sign, y_fwd, cost, test_month, threshold):
    """Fixed causal entry/side/scoring around a program's residual."""
    z = standardise(residual)
    y_fwd = np.asarray(y_fwd, float); cost = np.asarray(cost, float)
    valid = np.isfinite(z) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(z) >= float(threshold))
    side = -np.sign(z) * int(usd_sign)
    net = side * y_fwd - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})
