#!/usr/bin/env python3
"""
Early-exit penalty analysis for MOM trades.
Measures whether active-leg PnL would have improved after Z-exit.

Outputs:
- data/analysis/m5_exit_penalty_summary.csv
- data/analysis/m5_exit_penalty_by_pair.csv
- data/analysis/m15_exit_penalty_summary.csv
- data/analysis/m15_exit_penalty_by_pair.csv
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m5 as m5
from pipelines import build_events_m15 as m15


@dataclass
class TFConfig:
    label: str
    events_path: str
    module: object
    lookahead: int


CONFIGS = [
    TFConfig("m5", "data/events/events_m5_8yr_v3_mom.csv", m5, 20),
    TFConfig("m15", "data/events/events_m15_8yr_v3_mom.csv", m15, 20),
]

OUT_DIR = "data/analysis"
THRESHOLDS = [5.0, 10.0, 20.0]


def _load_prices(module, fx, fy, cx, cy):
    df = module.load_pair_data(fx, fy, cx, cy)
    if df is None:
        return None
    x = np.log(df["X"].to_numpy())
    y = np.log(df["Y"].to_numpy())
    ts = df["timestamp"].to_numpy()
    if np.issubdtype(ts.dtype, np.datetime64):
        ts = ts.astype("datetime64[ns]").astype("int64")
    else:
        ts = ts.astype("int64")
    return ts, x, y


def _pair_map(module):
    return {name: (fx, fy, cx, cy) for name, fx, fy, cx, cy, *_ in module.PAIRS}


def _analyze(cfg: TFConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(
        cfg.events_path,
        usecols=["pair", "timestamp", "active_leg", "side", "duration_bars"],
    )
    df["timestamp"] = df["timestamp"].astype("int64")

    pair_info = _pair_map(cfg.module)
    rows = []

    for pair, sub in df.groupby("pair"):
        if pair not in pair_info:
            continue
        fx, fy, cx, cy = pair_info[pair]
        loaded = _load_prices(cfg.module, fx, fy, cx, cy)
        if loaded is None:
            continue
        ts, x, y = loaded
        idx_map = {int(t): i for i, t in enumerate(ts)}

        for _, row in sub.iterrows():
            entry_ts = int(row["timestamp"])
            entry_idx = idx_map.get(entry_ts)
            if entry_idx is None:
                continue
            exit_idx = entry_idx + int(row["duration_bars"])
            if exit_idx >= len(ts):
                continue

            direction = 1 if row["side"] == "LONG" else -1
            active_leg = row["active_leg"]
            active = y if active_leg == "Y" else x

            entry_price = active[entry_idx]
            pnl_exit = direction * (active[exit_idx] - entry_price) * 10000.0

            end_idx = min(exit_idx + cfg.lookahead, len(active) - 1)
            if end_idx <= exit_idx:
                max_after = pnl_exit
            else:
                future = direction * (active[exit_idx + 1 : end_idx + 1] - entry_price) * 10000.0
                max_after = float(np.max(future)) if len(future) else pnl_exit

            delta = max_after - pnl_exit
            rows.append(
                {
                    "pair": pair,
                    "delta": delta,
                    "pnl_exit": pnl_exit,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out, out

    summary = {
        "trades": len(out),
        "delta_mean": float(out["delta"].mean()),
        "delta_median": float(out["delta"].median()),
        "delta_p80": float(out["delta"].quantile(0.8)),
        "delta_p95": float(out["delta"].quantile(0.95)),
    }
    for t in THRESHOLDS:
        summary[f"delta_gt_{int(t)}"] = float((out["delta"] > t).mean())
    summary_df = pd.DataFrame([summary])

    by_pair = out.groupby("pair").agg(
        trades=("pair", "count"),
        delta_mean=("delta", "mean"),
        delta_median=("delta", "median"),
        delta_p80=("delta", lambda s: s.quantile(0.8)),
        delta_gt_5=("delta", lambda s: (s > 5.0).mean()),
        delta_gt_10=("delta", lambda s: (s > 10.0).mean()),
        delta_gt_20=("delta", lambda s: (s > 20.0).mean()),
    ).reset_index()

    return summary_df, by_pair


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for cfg in CONFIGS:
        summary, by_pair = _analyze(cfg)
        summary_path = os.path.join(OUT_DIR, f"{cfg.label}_exit_penalty_summary.csv")
        pair_path = os.path.join(OUT_DIR, f"{cfg.label}_exit_penalty_by_pair.csv")
        summary.to_csv(summary_path, index=False)
        by_pair.to_csv(pair_path, index=False)
        print(f"Saved: {summary_path}")
        print(f"Saved: {pair_path}")


if __name__ == "__main__":
    main()
