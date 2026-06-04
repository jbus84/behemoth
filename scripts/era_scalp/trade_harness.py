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


def _apply_fill_lag(fwd: np.ndarray, fill_lag: int) -> np.ndarray:
    """Shift forward returns so a decision at bar t realizes the move from t+fill_lag
    (models execution latency: decide now, fill `fill_lag` bars later)."""
    if fill_lag <= 0:
        return fwd
    out = np.full_like(fwd, np.nan)
    if fwd.shape[0] > fill_lag:
        out[: fwd.shape[0] - fill_lag] = fwd[fill_lag:]
    return out


def expanding_quantile_threshold(
    signal: np.ndarray, q: float, warmup: int = 2000, recompute_every: int = 500
) -> np.ndarray:
    """Causal per-bar conviction threshold.

    At bar t the threshold is the q-quantile of |signal[:t+1]| over the finite
    values seen so far. To bound cost it is recomputed every `recompute_every`
    bars and held constant between recomputes. Returns NaN (no-trade) until at
    least `warmup` finite samples have accrued. Uses only past data, so a future
    perturbation can never change a past threshold value.
    """
    a = np.abs(np.asarray(signal, float))
    n = a.shape[0]
    thr = np.full(n, np.nan)
    fin = np.isfinite(a)
    cum_fin = np.cumsum(fin)
    last = np.nan
    for t in range(n):
        if cum_fin[t] < warmup:
            continue
        if not np.isfinite(last) or (t % recompute_every == 0):
            hist = a[: t + 1][fin[: t + 1]]
            last = float(np.quantile(hist, q))
        thr[t] = last
    return thr


def evaluate_trades(signal, mid, cost, test_month, pip, q, h,
                    causal_threshold=False, warmup=2000, recompute_every=500, fill_lag=0):
    """Top-q |conviction| entries; side=sign(signal); exit at t+h; net = side*fwd - cost.

    causal_threshold=False (default): conviction cutoff is the full-sample q-quantile
    of |scaled signal| (legacy; uses look-ahead, kept for A/B and backward compat).
    causal_threshold=True: cutoff is a causal expanding-window quantile (no look-ahead).
    fill_lag=0 (default): decide and fill at bar t. fill_lag=k: decide at bar t but fill
    k bars later (models execution latency), realizing the move from t+k instead of t.
    """
    raw = np.asarray(signal, float)
    s = scale_signal(raw)
    fwd = forward_return(mid, pip, h)
    fwd = _apply_fill_lag(fwd, fill_lag)
    cost = np.asarray(cost, float)
    fin = np.isfinite(s)
    if fin.sum() < 2:
        return pd.DataFrame({"net": np.array([]), "test_month": np.array([])})
    if causal_threshold:
        thr = expanding_quantile_threshold(s, q, warmup=warmup, recompute_every=recompute_every)
        armed = np.isfinite(thr)
        entry = fin & np.isfinite(fwd) & np.isfinite(cost) & armed & (np.abs(s) >= thr)
    else:
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
                                deviation_mode="absolute", causal_threshold=False, warmup=2000, recompute_every=500, fill_lag=0):
    """Trade when fair deviates from mid.

    The program's `fair_price` is a synthetic price index (e.g. cumsum of
    vel_pips_h1).  We align it with `mid` by converting mid to pips-from-start
    so the two series are directly comparable. Supports opt-in causal expanding-quantile threshold.

    Parameters
    ----------
    fair_price : np.ndarray
        Estimated fair price at each bar (synthetic price index, same units
        as cumsum of returns in pips).
    mid : np.ndarray
        Observed mid price (raw price, e.g. 1.0850).
    deviation_mode : str
        "absolute" = threshold on |deviation|; "relative" = threshold on |deviation| / spread.
    fill_lag : int
        Default 0 (decide and fill at bar t). If k > 0, decide at bar t but fill k bars
        later, realizing the move from t+k instead of t (models execution latency).
    """
    fair = np.asarray(fair_price, float)
    mid_arr = np.asarray(mid, float)
    cost_arr = np.asarray(cost, float)
    fwd = forward_return(mid_arr, pip, h)
    fwd = _apply_fill_lag(fwd, fill_lag)

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
    if causal_threshold:
        thr = expanding_quantile_threshold(abs_dev, q, warmup=warmup, recompute_every=recompute_every)
        entry = fin & np.isfinite(thr) & (abs_dev >= thr)
    else:
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


