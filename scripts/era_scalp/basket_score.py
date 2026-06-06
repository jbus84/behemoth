from __future__ import annotations

import numpy as np
import pandas as pd


def rank_to_weights(s: np.ndarray, k: int) -> np.ndarray:
    """Dollar-neutral top-k/bottom-k weights: long top-k (+1/k), short bottom-k (-1/k).

    Returns all-zero (flat) when fewer than 2*k finite scores are available."""
    s = np.asarray(s, float)
    m = s.shape[0]
    w = np.zeros(m)
    finite = np.where(np.isfinite(s))[0]
    if finite.size < 2 * k:
        return w
    order = finite[np.argsort(s[finite], kind="stable")]
    shorts = order[:k]
    longs = order[-k:]
    w[longs] = 1.0 / k
    w[shorts] = -1.0 / k
    return w


def apply_band(prev_w: np.ndarray, target_w: np.ndarray, band: float) -> np.ndarray:
    """Book-level L1 turnover band: carry prev weights unless the L1 distance to the
    fresh target exceeds `band`. Both prev and target are dollar-neutral, so the carried
    book stays neutral. band=0 -> always rebalance; large band -> rarely rebalance."""
    if float(np.abs(np.asarray(target_w) - np.asarray(prev_w)).sum()) <= band:
        return np.asarray(prev_w, float)
    return np.asarray(target_w, float)


def _session_ok(hour_val, session) -> bool:
    if session is None:
        return True
    lo, hi = session
    return bool(lo <= hour_val < hi)


def periodic_rebalance(scores, split, h, *, k, band, fill_mode, passive_frac, session):
    """Periodic rebalance at horizon h. Step in non-overlapping blocks of h bars;
    form dollar-neutral top-k/bottom-k weights, apply the turnover band, and book
    net = (gross forward P&L) - (turnover * per-leg cost). One row per rebalance.

    fill_mode: 'aggressive' charges the full cost_panel spread; 'passive' charges
    passive_frac of it (earning rather than paying part of the spread)."""
    scores = np.asarray(scores, float)
    y = np.asarray(split.y_fwd_panel, float)
    cost = np.asarray(split.cost_panel, float)
    tm = np.asarray(split.test_month)
    hour = split.hour
    n, m = scores.shape
    prev_w = np.zeros(m)
    nets, months = [], []
    for t in range(0, n - h, h):
        if session is not None and (hour is None or not _session_ok(hour[t], session)):
            continue
        s = scores[t]
        if not np.isfinite(s).any():
            continue
        target = rank_to_weights(s, k)
        w = apply_band(prev_w, target, band)
        gross = float(np.nansum(w * y[t]))
        turn = np.abs(w - prev_w)
        per_leg = cost[t] if fill_mode == "aggressive" else cost[t] * passive_frac
        c = float(np.nansum(turn * per_leg))
        nets.append(gross - c)
        months.append(tm[t])
        prev_w = w
    return pd.DataFrame({"net": np.asarray(nets, float), "test_month": np.asarray(months)})


def make_basket_score_frame(*, k, band, fill_mode, passive_frac, session,
                            holding_model=periodic_rebalance):
    """Bind basket parameters into the engine's (out, split, q, h) score_frame signature.

    q is unused (k/band/fill are RunSpec-fixed, not grid-swept). holding_model is the
    swappable P&L strategy; periodic_rebalance is v1."""
    def score_frame(out, split, q, h):
        return holding_model(out, split, h, k=k, band=band, fill_mode=fill_mode,
                             passive_frac=passive_frac, session=session)
    return score_frame
