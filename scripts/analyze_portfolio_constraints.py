#!/usr/bin/env python3
"""
Portfolio-level constraints: max concurrent trades and per-leg caps.
Outputs:
- data/analysis/m5_portfolio_constraints.csv
- data/analysis/m15_portfolio_constraints.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
from pipelines import build_events_m5 as m5
from pipelines import build_events_m15 as m15

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 14

MAX_CONCURRENT = [5, 10, 20]
LEG_CAPS = [1, 2, 3]

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", m15, 15),
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


def _apply_guardrail(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("exit_ts").copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
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


def _pair_map(module):
    return {name: (fx, fy) for name, fx, fy, *_ in module.PAIRS}


def _apply_concurrent_cap(df: pd.DataFrame, max_open: int) -> pd.DataFrame:
    df = df.sort_values("timestamp").copy()
    active = []
    kept = []
    for row in df.itertuples(index=False):
        now = int(row.timestamp)
        active = [t for t in active if t[1] > now]
        if len(active) >= max_open:
            continue
        kept.append(row)
        active.append((row.timestamp, row.exit_ts))
    return pd.DataFrame(kept)


def _apply_leg_cap(df: pd.DataFrame, pair_legs: dict, cap: int) -> pd.DataFrame:
    df = df.sort_values("timestamp").copy()
    active = []
    kept = []
    open_by_leg = defaultdict(int)

    for row in df.itertuples(index=False):
        now = int(row.timestamp)
        active = [t for t in active if t[1] > now]
        open_by_leg = defaultdict(int)
        for _, end_ts, legs in active:
            for leg in legs:
                open_by_leg[leg] += 1

        legs = pair_legs.get(row.pair)
        if legs is None:
            continue
        if open_by_leg[legs[0]] >= cap or open_by_leg[legs[1]] >= cap:
            continue

        kept.append(row)
        active.append((row.timestamp, row.exit_ts, legs))
    return pd.DataFrame(kept)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        rows = []
        rows.append({"variant": "baseline", "guardrail": False, **_metrics(df)})
        rows.append({"variant": "baseline", "guardrail": True, **_metrics(_apply_guardrail(df))})

        for max_open in MAX_CONCURRENT:
            filtered = _apply_concurrent_cap(df, max_open)
            rows.append({"variant": f"cap_concurrent_{max_open}", "guardrail": False, **_metrics(filtered)})
            rows.append({"variant": f"cap_concurrent_{max_open}", "guardrail": True, **_metrics(_apply_guardrail(filtered))})

        pair_legs = _pair_map(module)
        for cap in LEG_CAPS:
            filtered = _apply_leg_cap(df, pair_legs, cap)
            rows.append({"variant": f"cap_leg_{cap}", "guardrail": False, **_metrics(filtered)})
            rows.append({"variant": f"cap_leg_{cap}", "guardrail": True, **_metrics(_apply_guardrail(filtered))})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_portfolio_constraints.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_portfolio_constraints.csv")


if __name__ == "__main__":
    main()
