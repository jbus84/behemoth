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
