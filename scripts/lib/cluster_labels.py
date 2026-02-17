#!/usr/bin/env python3
"""Cluster-label builders for pre-entry loss-cluster prediction."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


_REQUIRED_COLS = {"timestamp", "exit_ts", "pnl_bps", "pair", "timeframe", "strategy_type"}


def _require_columns(df: pd.DataFrame, extra: Sequence[str] = ()) -> None:
    need = set(_REQUIRED_COLS).union(set(extra))
    missing = sorted([c for c in need if c not in df.columns])
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def build_cluster_trade_labels(
    df: pd.DataFrame,
    horizon_trades: int = 10,
    loss_bps: float = -250.0,
    group_cols: Sequence[str] = ("pair", "timeframe", "strategy_type"),
) -> pd.Series:
    """
    Label whether the next `horizon_trades` trades form a losing cluster.

    Label definition (per group):
    - 1 if cumulative pnl_bps of next H trades <= loss_bps
    - 0 otherwise
    - <NA> when fewer than H future trades exist
    """
    _require_columns(df)
    if horizon_trades <= 0:
        raise ValueError("horizon_trades must be > 0")

    labels = pd.Series(pd.NA, index=df.index, dtype="Int64")
    if df.empty:
        return labels

    order_cols = list(group_cols) + ["timestamp", "exit_ts"]
    ordered = df.sort_values(order_cols)

    for _, g in ordered.groupby(list(group_cols), sort=False):
        gidx = g.index.to_numpy()
        pnl = pd.to_numeric(g["pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        n = len(pnl)
        if n <= horizon_trades:
            continue

        csum = np.concatenate([[0.0], np.cumsum(pnl, dtype=float)])
        i = np.arange(0, n - horizon_trades, dtype=int)
        next_h_sum = csum[i + horizon_trades + 1] - csum[i + 1]
        y = (next_h_sum <= float(loss_bps)).astype("int64")
        labels.loc[gidx[i]] = y

    return labels


def build_cluster_day_labels(
    df: pd.DataFrame,
    horizon_days: int = 5,
    loss_bps: float = -400.0,
    group_cols: Sequence[str] = ("pair", "timeframe", "strategy_type"),
) -> pd.Series:
    """
    Label whether the next D calendar days contain a severe daily loss cluster.

    Label definition (per group):
    - Build daily pnl curve from trade exits.
    - For each trade, inspect days [entry_day, entry_day + D - 1].
    - 1 if worst daily pnl in window <= loss_bps
    - 0 otherwise
    - <NA> when full D-day lookahead is not available.
    """
    _require_columns(df)
    if horizon_days <= 0:
        raise ValueError("horizon_days must be > 0")

    labels = pd.Series(pd.NA, index=df.index, dtype="Int64")
    if df.empty:
        return labels

    order_cols = list(group_cols) + ["timestamp", "exit_ts"]
    ordered = df.sort_values(order_cols)

    for _, g in ordered.groupby(list(group_cols), sort=False):
        gidx = g.index.to_numpy()
        entry_day = pd.to_datetime(g["timestamp"].to_numpy(dtype="int64"), unit="ns", utc=True).normalize()
        exit_day = pd.to_datetime(g["exit_ts"].to_numpy(dtype="int64"), unit="ns", utc=True).normalize()
        pnl = pd.to_numeric(g["pnl_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

        daily = (
            pd.DataFrame({"day": exit_day, "pnl_bps": pnl})
            .groupby("day", sort=True)["pnl_bps"]
            .sum()
            .sort_index()
        )
        if daily.empty:
            continue

        start_day = min(daily.index.min(), entry_day.min())
        end_day = max(daily.index.max(), entry_day.max())
        all_days = pd.date_range(start_day, end_day, freq="D", tz="UTC")
        daily_full = daily.reindex(all_days, fill_value=0.0)
        arr = daily_full.to_numpy(dtype=float)

        day_to_pos = {d: i for i, d in enumerate(all_days)}
        n_days = len(arr)

        # Forward rolling minimum over fixed horizon.
        fwd_min = np.full(n_days, np.nan, dtype=float)
        last_valid_start = n_days - horizon_days
        if last_valid_start >= 0:
            for i in range(0, last_valid_start + 1):
                fwd_min[i] = float(np.min(arr[i : i + horizon_days]))

        for row_i, d in zip(gidx, entry_day):
            pos = day_to_pos.get(d)
            if pos is None or pos > last_valid_start:
                continue
            labels.at[row_i] = int(fwd_min[pos] <= float(loss_bps))

    return labels


def label_distribution(y: pd.Series) -> dict[str, float]:
    """Return simple class distribution for Int64 labels with NAs."""
    s = pd.Series(y)
    out = {
        "n_total": int(len(s)),
        "n_labeled": int(s.notna().sum()),
        "label_rate_1": 0.0,
        "label_rate_0": 0.0,
    }
    labeled = s.dropna().astype(int)
    if labeled.empty:
        return out
    out["label_rate_1"] = float((labeled == 1).mean())
    out["label_rate_0"] = float((labeled == 0).mean())
    return out
