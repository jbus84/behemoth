from __future__ import annotations

import numpy as np
import pandas as pd


def standardise(resid: np.ndarray) -> np.ndarray:
    r = np.asarray(resid, dtype=float)
    finite = np.isfinite(r)
    if finite.sum() < 2:
        return np.full_like(r, np.nan)
    mu = r[finite].mean()
    sd = r[finite].std(ddof=0)
    if sd == 0:
        return np.zeros_like(r)
    return (r - mu) / sd


def evaluate_residual(residual, usd_sign, y_fwd, cost, test_month, threshold):
    """Fixed causal entry/side/scoring around a program's residual."""
    z = standardise(residual)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(z) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(z) >= float(threshold))
    side = -np.sign(z) * int(usd_sign)
    net = side * y_fwd - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})


def entry_diagnostics(residual, dispersion, usd_sign, y_fwd, cost, test_month, threshold):
    """ADR 0005 dispersion diagnostics for the bars a program would trade."""
    z = standardise(residual)
    dispersion = np.asarray(dispersion, float)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(z) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(z) >= float(threshold))
    n = int(entry.sum())
    if n == 0:
        return {"n_entries": 0, "mean_dispersion_at_entry": float("nan"),
                "mean_net": float("nan"), "month_hit_rate": float("nan")}
    side = -np.sign(z) * int(usd_sign)
    net = (side * y_fwd - cost)[entry]
    months = np.asarray(test_month)[entry]
    monthly = pd.Series(net).groupby(months).mean()
    return {
        "n_entries": n,
        "mean_dispersion_at_entry": float(np.nanmean(dispersion[entry])),
        "mean_net": float(net.mean()),
        "month_hit_rate": float((monthly > 0).mean()),
    }


_FLOOR = -1e6
_N0 = 100


def task_score(df: pd.DataFrame) -> float:
    """Continuous, permissive per-node signal. NEVER a hard gate."""
    n = len(df)
    if n < 2:
        return _FLOOR + n  # finite, slightly rewards 'some entries' over none
    net = df["net"].to_numpy(float)
    mean = net.mean()
    se = net.std(ddof=1) / np.sqrt(n)
    net_lb95 = mean - 1.645 * se
    monthly = df.groupby("test_month")["net"].mean()
    month_weight = float((monthly > 0).mean())  # in [0,1]
    n_weight = n / (n + _N0)  # smooth saturation
    # keep continuous & signed: a positive lb95 with consistent months scores high
    return float(net_lb95 * (0.25 + 0.75 * month_weight) * n_weight)
