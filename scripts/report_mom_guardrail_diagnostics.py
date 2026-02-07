#!/usr/bin/env python3
"""
Diagnostics for MOM loss-streak guardrail (M15).

Outputs:
- data/analysis/mom_guardrail_overall.csv
- data/analysis/mom_guardrail_monthly.csv
- data/analysis/mom_guardrail_session.csv
- data/analysis/mom_guardrail_symbol.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

DATA_PATH = "data/meta_model/events_m15_8yr_v3_mom.csv"
OUT_DIR = "data/analysis"

LOSS_STREAK = 3
COOLDOWN_DAYS = 14

SESSIONS = [
    ("Asia", 0, 7),
    ("London", 7, 13),
    ("New_York", 13, 21),
    ("Late", 21, 24),
]


def _session_name(hour: int) -> str:
    for name, start, end in SESSIONS:
        if start <= hour < end:
            return name
    return "Unknown"


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(
            trades=0,
            win_rate=0.0,
            mean_pnl=0.0,
            total_pnl=0.0,
            max_dd=0.0,
            sharpe=0.0,
            sharpe_active=0.0,
            sharpe_trade=0.0,
        )
    pnl = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        win_rate=float((pnl > 0).mean() * 100.0),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def _apply_guardrail(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("exit_ts").copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for _, row in df.iterrows():
        pair = row["pair"]
        ts = int(row["exit_ts"])
        pnl = float(row["pnl_bps"])

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        keep.append(row)

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    if not keep:
        return df.iloc[:0]
    return pd.DataFrame(keep)


def _aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, sub in df.groupby(group_cols, dropna=False):
        metrics = _metrics(sub.sort_values("exit_ts"))
        if not isinstance(key, tuple):
            key = (key,)
        row = {col: val for col, val in zip(group_cols, key)}
        row.update(metrics)
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = df["timestamp"].astype("int64")
    df["exit_ts"] = df["timestamp"] + (df["duration_bars"].astype(int) * 15 * 60 * 1_000_000_000)
    df["entry_dt"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce")
    df["exit_dt"] = pd.to_datetime(df["exit_ts"], unit="ns", utc=True, errors="coerce")
    df["year_month"] = df["exit_dt"].dt.to_period("M").astype(str)
    df["session"] = df["hour"].map(_session_name)

    base = df.sort_values("exit_ts").copy()
    guard = _apply_guardrail(df)

    overall = []
    for label, sub in [("baseline", base), ("loss_streak_3_14d", guard)]:
        row = {"variant": label}
        row.update(_metrics(sub))
        overall.append(row)
    pd.DataFrame(overall).to_csv(os.path.join(OUT_DIR, "mom_guardrail_overall.csv"), index=False)

    monthly = []
    for label, sub in [("baseline", base), ("loss_streak_3_14d", guard)]:
        agg = _aggregate(sub, ["year_month"])
        agg["variant"] = label
        monthly.append(agg)
    pd.concat(monthly, ignore_index=True).to_csv(
        os.path.join(OUT_DIR, "mom_guardrail_monthly.csv"), index=False
    )

    session = []
    for label, sub in [("baseline", base), ("loss_streak_3_14d", guard)]:
        agg = _aggregate(sub, ["session"])
        agg["variant"] = label
        session.append(agg)
    pd.concat(session, ignore_index=True).to_csv(
        os.path.join(OUT_DIR, "mom_guardrail_session.csv"), index=False
    )

    symbol = []
    for label, sub in [("baseline", base), ("loss_streak_3_14d", guard)]:
        agg = _aggregate(sub, ["pair"])
        agg["variant"] = label
        symbol.append(agg)
    pd.concat(symbol, ignore_index=True).to_csv(
        os.path.join(OUT_DIR, "mom_guardrail_symbol.csv"), index=False
    )

    print("Saved:")
    print("- data/analysis/mom_guardrail_overall.csv")
    print("- data/analysis/mom_guardrail_monthly.csv")
    print("- data/analysis/mom_guardrail_session.csv")
    print("- data/analysis/mom_guardrail_symbol.csv")


if __name__ == "__main__":
    main()
