"""Causal rolling primitives. Every output at index i uses only x[:i+1]."""

from __future__ import annotations

import numpy as np


def ewma_vol(x: np.ndarray, lam: float) -> np.ndarray:
    """Causal EWMA volatility of x. var_i = lam*var_{i-1} + (1-lam)*x_i^2; vol_0 = 0."""
    x = np.asarray(x, dtype=float)
    var = np.zeros_like(x)
    for i in range(1, len(x)):
        var[i] = lam * var[i - 1] + (1.0 - lam) * x[i] ** 2
    return np.sqrt(var)


def causal_zscore(x: np.ndarray, window: int) -> np.ndarray:
    """Trailing-window z-score: (x_i - mean(x[i-window+1:i+1])) / std(...). NaN until full."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        sd = w.std()
        out[i] = 0.0 if sd == 0 else (x[i] - w.mean()) / sd
    return out


def rolling_minmax_pos(x: np.ndarray, window: int) -> np.ndarray:
    """Position of x_i within its trailing window: (x_i - min) / (max - min) in [0, 1]."""
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, np.nan)
    for i in range(window - 1, len(x)):
        w = x[i - window + 1 : i + 1]
        lo, hi = w.min(), w.max()
        out[i] = 0.5 if hi == lo else (x[i] - lo) / (hi - lo)
    return out
