"""The ERA `score_frame`: turn a per-tick conviction signal into day-labelled net trades.

A program emits `signal(ctx) -> conviction[n_ticks]` (sign = direction, magnitude = conviction).
This executor converts it to trades with **tick-exact fills** and the same hysteresis-ride exits
that beat cost on trending days: enter the top-`q` conviction in the DRIFT regime, ride until a
hard stop / trailing give-back / confident reversal / `max_hold=h`, fill at ask (buy) / bid (sell).
Each trade's net is labelled by its day, so the ERA scorer's `fast_lower_bound` (mean-across-days
− z·SE) judges **day-robustness** for free.

Anti-mirage floors are the point of this module: a signal that trades too rarely (or on too few
distinct days) returns an EMPTY frame → `fast_lower_bound` is `nan` → the program is rejected.
That is the explicit guard against the "8× gross/cost on 10 lucky trades" cross-symbol mirage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from scripts.era_tick.era_panel import DRIFT_CODE, TickSplit

_EMPTY = pd.DataFrame({"net": np.array([]), "test_month": np.array([])})


def _threshold(s: np.ndarray, q: float) -> float | None:
    """Conviction cutoff = q-quantile of |s| over finite, NONZERO entries (0 = no opinion)."""
    nz = s[np.isfinite(s) & (s != 0.0)]
    if nz.size < 2:
        return None
    return float(np.quantile(np.abs(nz), q))


@dataclass(frozen=True, slots=True)
class ExitParams:
    stop_pips: float = 2.0
    trail_arm_pips: float = 2.0
    trail_give_pips: float = 1.5
    reversal_frac: float = 1.0  # exit if conviction flips to <= -reversal_frac * entry_thr


def _simulate(
    s: np.ndarray,
    split: TickSplit,
    regime: np.ndarray,
    thr: float,
    max_hold: int,
    ep: ExitParams,
    markup_pips: float,
) -> list[tuple[float, float, float, str]]:
    """Return one (net, gross, cost, day) tuple per round-trip trade."""
    pip, bid, ask, mid, day = split.pip, split.bid, split.ask, split.mid, split.day
    rev = ep.reversal_frac * thr
    trades: list[tuple[float, float, float, str]] = []
    pos = 0
    entry_fill = entry_mid = peak = 0.0
    entry_i = 0
    cur_day = None

    def close(i: int) -> None:
        nonlocal pos
        exit_fill = bid[i] if pos > 0 else ask[i]
        net = pos * (exit_fill - entry_fill) / pip - markup_pips
        gross = pos * (mid[i] - entry_mid) / pip
        trades.append((net, gross, gross - net, cur_day))
        pos = 0

    for i in range(len(s)):
        if day[i] != cur_day:
            if pos != 0:
                close(i - 1)
            cur_day = day[i]
        si = s[i]
        if pos == 0:
            if regime[i] == DRIFT_CODE and np.isfinite(si) and si != 0.0 and abs(si) >= thr:
                pos = 1 if si > 0 else -1
                entry_fill = ask[i] if pos > 0 else bid[i]
                entry_mid = mid[i]
                peak = 0.0
                entry_i = i
            continue
        unreal = pos * (mid[i] - entry_mid) / pip
        peak = max(peak, unreal)
        drawdown = peak - unreal
        if (
            unreal <= -ep.stop_pips
            or (peak >= ep.trail_arm_pips and drawdown >= ep.trail_give_pips)
            or (si * pos <= -rev)
            or (i - entry_i >= max_hold)
        ):
            close(i)
    if pos != 0:
        close(len(s) - 1)
    return trades


def make_score_frame(
    *,
    exit_params: ExitParams | None = None,
    markup_pips: float = 0.0,
    min_trades: int = 40,
    min_days: int = 8,
) -> Callable:
    """Build a `score_frame(out, split, q, h)` closure for the ERA `RunSpec`.

    q -> conviction quantile (top-|q| entries); h -> max-hold ticks. Floors reject thin signals.
    """
    ep = exit_params or ExitParams()
    reg_idx = None  # resolved per-call from split.names

    def score_frame(out, split: TickSplit, q: float, h: int) -> pd.DataFrame:
        nonlocal reg_idx
        if reg_idx is None:
            reg_idx = split.names.index("regime_code")
        s = np.asarray(out, float)
        regime = split.X[:, reg_idx]
        thr = _threshold(s, q)
        if thr is None:
            return _EMPTY
        trades = _simulate(s, split, regime, thr, int(h), ep, markup_pips)
        if len(trades) < min_trades:
            return _EMPTY
        frame = pd.DataFrame(trades, columns=["net", "gross", "cost", "test_month"])
        if frame["test_month"].nunique() < min_days:
            return _EMPTY
        return frame[["net", "test_month"]]

    return score_frame


def evaluate_full(
    out,
    split: TickSplit,
    q: float,
    h: int,
    *,
    exit_params: ExitParams | None = None,
    markup_pips: float = 0.0,
) -> pd.DataFrame:
    """Full per-trade frame (net, gross, cost, test_month) for reporting/decomposition.

    No floors applied — callers report n_trades / n_days alongside so thinness is visible.
    """
    ep = exit_params or ExitParams()
    s = np.asarray(out, float)
    regime = split.X[:, split.names.index("regime_code")]
    thr = _threshold(s, q)
    if thr is None:
        return pd.DataFrame(columns=["net", "gross", "cost", "test_month"])
    trades = _simulate(s, split, regime, thr, int(h), ep, markup_pips)
    return pd.DataFrame(trades, columns=["net", "gross", "cost", "test_month"])
