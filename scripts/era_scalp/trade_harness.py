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


def evaluate_fair_price_trades(fair_price, mid, cost, test_month, pip, q, h,
                                deviation_mode="absolute"):
    """Trade when fair deviates from mid.

    The program's `fair_price` is a synthetic price index (e.g. cumsum of
    vel_pips_h1).  We align it with `mid` by converting mid to pips-from-start
    so the two series are directly comparable.

    Parameters
    ----------
    fair_price : np.ndarray
        Estimated fair price at each bar (synthetic price index, same units
        as cumsum of returns in pips).
    mid : np.ndarray
        Observed mid price (raw price, e.g. 1.0850).
    deviation_mode : str
        "absolute" = threshold on |deviation|; "relative" = threshold on |deviation| / spread.
    """
    fair = np.asarray(fair_price, float)
    mid_arr = np.asarray(mid, float)
    cost_arr = np.asarray(cost, float)
    fwd = forward_return(mid_arr, pip, h)

    # Normalise mid to pips-from-first-valid so it lives in the same space as
    # fair (cumsum of bar returns in pips).
    fin_mid = np.isfinite(mid_arr)
    if not fin_mid.any():
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    base = mid_arr[fin_mid][0]
    mid_pips = np.full_like(mid_arr, np.nan, dtype=float)
    mid_pips[fin_mid] = (mid_arr[fin_mid] - base) / pip

    deviation = fair - mid_pips
    fin = np.isfinite(deviation) & np.isfinite(fwd) & np.isfinite(cost_arr)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    if deviation_mode == "absolute":
        abs_dev = np.abs(deviation)
    else:
        spread = cost_arr * 2.0  # cost = half-spread
        abs_dev = np.abs(deviation) / np.maximum(spread, 1e-12)
    thr = np.quantile(abs_dev[fin], q)
    entry = fin & (abs_dev >= thr)
    # Trade direction: buy when fair > mid (deviation > 0), sell when fair < mid
    net = np.sign(deviation) * fwd - cost_arr
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})


def per_symbol_net(sigs: dict, mids: dict, costs: dict, tms: dict, pips: dict, q, h) -> dict:
    out = {}
    for sym in sigs:
        df = evaluate_trades(sigs[sym], mids[sym], costs[sym], tms[sym], pips[sym], q, h)
        out[sym] = {"n": int(len(df)),
                    "mean_net": float(df["net"].mean()) if len(df) else float("nan")}
    return out
