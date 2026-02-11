#!/usr/bin/env python3
"""
Compare guardrail applied by entry_ts vs exit_ts ordering.
Outputs:
- data/analysis/m5_guardrail_entry_vs_exit.csv
- data/analysis/m15_guardrail_entry_vs_exit.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 14

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", 5),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", 15),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    pnl = df["pnl_bps"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def _apply_guardrail(df: pd.DataFrame, ts_field: str) -> pd.DataFrame:
    df = df.sort_values(ts_field).copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(getattr(row, ts_field))
        pnl = float(row.pnl_bps)

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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        base = df.sort_values("exit_ts")
        by_exit = _apply_guardrail(df, "exit_ts")
        by_entry = _apply_guardrail(df, "timestamp")

        rows = []
        for name, sub in [("baseline", base), ("guard_exit", by_exit), ("guard_entry", by_entry)]:
            row = {"variant": name}
            row.update(_metrics(sub))
            rows.append(row)

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_entry_vs_exit.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_guardrail_entry_vs_exit.csv")


if __name__ == "__main__":
    main()
