#!/usr/bin/env python3
"""Causal, realized-only cluster-state features."""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from collections.abc import Sequence

import numpy as np
import pandas as pd


_REQUIRED_COLS = {"pair", "timeframe", "strategy_type", "timestamp", "exit_ts", "pnl_bps"}


def _session_bucket_from_ts_ns(ts_ns: int) -> int:
    hour = int(pd.to_datetime(int(ts_ns), unit="ns", utc=True).hour)
    if 0 <= hour < 7:
        return 0
    if 7 <= hour < 13:
        return 1
    if 13 <= hour < 21:
        return 2
    return 3


def _safe_tail_sum(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    return float(np.sum(values[-n:]))


def _safe_tail_std(values: list[float], n: int) -> float:
    if len(values) < 2:
        return 0.0
    tail = np.asarray(values[-n:], dtype=float)
    if len(tail) < 2:
        return 0.0
    return float(np.std(tail, ddof=1))


def _dd_from_local_peak(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    tail = np.asarray(values[-n:], dtype=float)
    curve = np.cumsum(tail)
    peak = np.maximum.accumulate(curve)
    return float(curve[-1] - peak[-1])


def _require_columns(df: pd.DataFrame) -> None:
    missing = sorted([c for c in _REQUIRED_COLS if c not in df.columns])
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def add_cluster_state_features(
    df: pd.DataFrame,
    group_cols: Sequence[str] = ("pair", "timeframe", "strategy_type"),
) -> pd.DataFrame:
    """
    Add causal cluster-state features at each entry timestamp.

    Feature semantics:
    - realized_* metrics are based only on trades with exit_ts <= current entry timestamp.
    - no open/unrealized trade outcomes are used.
    """
    _require_columns(df)
    if df.empty:
        out = df.copy()
        for c in [
            "realized_loss_streak_3",
            "realized_pnl_sum_5",
            "realized_pnl_sum_10",
            "realized_pnl_sum_20",
            "realized_dd_from_local_peak_20",
            "trade_arrival_rate_1d",
            "trade_arrival_rate_3d",
            "recent_vol_proxy_20",
            "session_loss_rate_20",
        ]:
            out[c] = np.nan
        return out

    out = df.copy()
    order_cols = list(group_cols) + ["timestamp", "exit_ts"]

    for col in [
        "realized_loss_streak_3",
        "realized_pnl_sum_5",
        "realized_pnl_sum_10",
        "realized_pnl_sum_20",
        "realized_dd_from_local_peak_20",
        "trade_arrival_rate_1d",
        "trade_arrival_rate_3d",
        "recent_vol_proxy_20",
        "session_loss_rate_20",
    ]:
        out[col] = 0.0

    ordered = out.sort_values(order_cols)
    one_day_ns = int(pd.Timedelta(days=1).value)
    three_day_ns = int(pd.Timedelta(days=3).value)

    for _, g in ordered.groupby(list(group_cols), sort=False):
        gidx = g.index.to_numpy()
        ts = pd.to_numeric(g["timestamp"], errors="coerce").fillna(0).to_numpy(dtype="int64")
        ex = pd.to_numeric(g["exit_ts"], errors="coerce").fillna(0).to_numpy(dtype="int64")
        pnl = pd.to_numeric(g["pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

        session = np.asarray([_session_bucket_from_ts_ns(t) for t in ts], dtype=int)

        pending: list[tuple[int, float, int, int]] = []  # (exit_ts, pnl, entry_ts, session)
        realized_pnls: list[float] = []
        realized_exit_ts: deque[int] = deque()
        current_loss_streak = 0
        session_recent: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=20))

        feat_loss_streak = np.zeros(len(gidx), dtype=float)
        feat_sum5 = np.zeros(len(gidx), dtype=float)
        feat_sum10 = np.zeros(len(gidx), dtype=float)
        feat_sum20 = np.zeros(len(gidx), dtype=float)
        feat_dd20 = np.zeros(len(gidx), dtype=float)
        feat_rate1d = np.zeros(len(gidx), dtype=float)
        feat_rate3d = np.zeros(len(gidx), dtype=float)
        feat_vol20 = np.zeros(len(gidx), dtype=float)
        feat_sess_loss20 = np.zeros(len(gidx), dtype=float)

        for i in range(len(gidx)):
            t = int(ts[i])

            while pending and pending[0][0] <= t:
                _, rpnl, rexit_ts, rsess = heapq.heappop(pending)
                realized_pnls.append(float(rpnl))
                realized_exit_ts.append(int(rexit_ts))
                is_loss = 1 if float(rpnl) <= 0.0 else 0
                if is_loss:
                    current_loss_streak += 1
                else:
                    current_loss_streak = 0
                session_recent[int(rsess)].append(is_loss)

            while realized_exit_ts and realized_exit_ts[0] < t - three_day_ns:
                realized_exit_ts.popleft()

            feat_loss_streak[i] = float(min(current_loss_streak, 3))
            feat_sum5[i] = _safe_tail_sum(realized_pnls, 5)
            feat_sum10[i] = _safe_tail_sum(realized_pnls, 10)
            feat_sum20[i] = _safe_tail_sum(realized_pnls, 20)
            feat_dd20[i] = _dd_from_local_peak(realized_pnls, 20)
            feat_vol20[i] = _safe_tail_std(realized_pnls, 20)

            n3 = len(realized_exit_ts)
            n1 = 0
            if n3:
                cutoff_1d = t - one_day_ns
                n1 = sum(1 for z in realized_exit_ts if z >= cutoff_1d)
            feat_rate1d[i] = float(n1)
            feat_rate3d[i] = float(n3 / 3.0)

            sess_hist = session_recent[int(session[i])]
            feat_sess_loss20[i] = float(np.mean(sess_hist)) if sess_hist else 0.5

            heapq.heappush(pending, (int(ex[i]), float(pnl[i]), int(ex[i]), int(session[i])))

        out.loc[gidx, "realized_loss_streak_3"] = feat_loss_streak
        out.loc[gidx, "realized_pnl_sum_5"] = feat_sum5
        out.loc[gidx, "realized_pnl_sum_10"] = feat_sum10
        out.loc[gidx, "realized_pnl_sum_20"] = feat_sum20
        out.loc[gidx, "realized_dd_from_local_peak_20"] = feat_dd20
        out.loc[gidx, "trade_arrival_rate_1d"] = feat_rate1d
        out.loc[gidx, "trade_arrival_rate_3d"] = feat_rate3d
        out.loc[gidx, "recent_vol_proxy_20"] = feat_vol20
        out.loc[gidx, "session_loss_rate_20"] = feat_sess_loss20

    return out
