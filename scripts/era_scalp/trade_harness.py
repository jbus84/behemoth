from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era_scalp.harness import scale_signal, task_score


def forward_return(mid: np.ndarray, pip: float, h: int) -> np.ndarray:
    """(mid[t+h] - mid[t]) / pip; NaN for the last h bars."""
    mid = np.asarray(mid, float)
    n = mid.shape[0]
    out = np.full(n, np.nan)
    if n > h:
        out[: n - h] = (mid[h:] - mid[: n - h]) / pip
    return out


def evaluate_trades(signal, mid, cost, test_month, pip, q, h):
    """Top-q |conviction| entries; side=sign(signal); exit at t+h; net = side*fwd - cost."""
    raw = np.asarray(signal, float)
    s = scale_signal(raw)
    fwd = forward_return(mid, pip, h)
    cost = np.asarray(cost, float)
    fin = np.isfinite(s)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    thr = np.quantile(np.abs(s[fin]), q)
    entry = fin & np.isfinite(fwd) & np.isfinite(cost) & (np.abs(s) >= thr)
    net = np.sign(raw) * fwd - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})


def pooled_task_score(frames: list[pd.DataFrame]) -> float:
    nz = [f for f in frames if len(f)]
    if not nz:
        return task_score(pd.DataFrame({"net": np.array([]), "test_month": np.array([])}))
    return task_score(pd.concat(nz, ignore_index=True))


def per_symbol_net(sigs: dict, mids: dict, costs: dict, tms: dict, pips: dict, q, h) -> dict:
    out = {}
    for sym in sigs:
        df = evaluate_trades(sigs[sym], mids[sym], costs[sym], tms[sym], pips[sym], q, h)
        out[sym] = {"n": int(len(df)),
                    "mean_net": float(df["net"].mean()) if len(df) else float("nan")}
    return out


def evaluate_fair_price_trades(fair_price, mid, cost, test_month, pip, q, h,
                                deviation_mode="absolute"):
    """Fair-price deviation trading.

    fair_price[t] = estimated fair price at bar t (in same units as mid).
    deviation[t] = fair_price[t] - mid[t] (positive = price below fair).
    Entry when |deviation| > threshold, direction = sign(deviation).
    Exit at t+h.

    Parameters
    ----------
    deviation_mode : str
        "absolute" = threshold on raw deviation in pips.
        "relative" = threshold on deviation / rolling_std(deviation).
    """
    fair = np.asarray(fair_price, float)
    mid_arr = np.asarray(mid, float)
    dev = (fair - mid_arr) / pip  # deviation in pips

    fwd = forward_return(mid_arr, pip, h)
    cost_arr = np.asarray(cost, float)

    fin = np.isfinite(dev)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})

    if deviation_mode == "relative":
        # Normalise deviation by rolling standard deviation
        window = max(h * 5, 50)
        roll_std = pd.Series(dev).rolling(window=window, min_periods=10).std().values
        roll_std = np.where(np.isfinite(roll_std) & (roll_std > 0), roll_std, 1.0)
        norm_dev = dev / roll_std
        thr = np.quantile(np.abs(norm_dev[fin]), q)
        entry = fin & np.isfinite(fwd) & np.isfinite(cost_arr) & (np.abs(norm_dev) >= thr)
        # Direction: fair > mid → buy (dev > 0), fair < mid → sell (dev < 0)
        side = np.sign(dev)
    else:
        # Absolute deviation in pips
        thr = np.quantile(np.abs(dev[fin]), q)
        entry = fin & np.isfinite(fwd) & np.isfinite(cost_arr) & (np.abs(dev) >= thr)
        side = np.sign(dev)

    net = side * fwd - cost_arr
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})
