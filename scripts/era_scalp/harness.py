from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era.harness import task_score  # reuse the dispersion TaskScore unchanged

__all__ = ["scale_signal", "evaluate_signal", "entry_diagnostics", "task_score"]


def scale_signal(signal: np.ndarray) -> np.ndarray:
    """MAD-scale (no mean-centering) so the program's directional sign is preserved."""
    s = np.asarray(signal, dtype=float)
    finite = np.isfinite(s)
    if finite.sum() < 2:
        return np.full_like(s, np.nan)
    med = np.median(s[finite])
    mad = np.median(np.abs(s[finite] - med))
    scale = 1.4826 * mad
    if scale <= 0:
        return np.full_like(s, np.nan)
    return s / scale


def evaluate_signal(signal, y_fwd, cost, test_month, threshold):
    """Directional entry/side/scoring: side = sign(signal); net = side*y_fwd - cost."""
    raw = np.asarray(signal, dtype=float)
    s = scale_signal(raw)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(s) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(s) >= float(threshold))
    side = np.sign(raw)
    net = side * y_fwd - cost
    return pd.DataFrame(
        {"net": net[entry], "test_month": np.asarray(test_month)[entry]}
    )


def entry_diagnostics(signal, y_fwd, cost, test_month, threshold):
    """Scalping diagnostics for the bars a program would trade."""
    raw = np.asarray(signal, dtype=float)
    s = scale_signal(raw)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(s) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(s) >= float(threshold))
    n = int(entry.sum())
    if n == 0:
        return {"n_entries": 0, "hit_rate": float("nan"), "mean_net": float("nan"),
                "mean_cost": float("nan"), "month_hit_rate": float("nan")}
    side = np.sign(raw)[entry]
    yf = y_fwd[entry]
    net = side * yf - cost[entry]
    months = np.asarray(test_month)[entry]
    monthly = pd.Series(net).groupby(months).mean()
    return {
        "n_entries": n,
        "hit_rate": float((side * yf > 0).mean()),
        "mean_net": float(net.mean()),
        "mean_cost": float(cost[entry].mean()),
        "month_hit_rate": float((monthly > 0).mean()),
    }
