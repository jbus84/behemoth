#!/usr/bin/env python3
"""
Counterfactual exit analysis for MOM trades.
Compare actual Z-based exit PnL vs active-leg-only breakeven exit.

Active-leg exit rule:
- Exit when active-leg PnL crosses <= 0 (breakeven or worse)
- If never crosses within max_hold bars, exit at max_hold

Outputs:
- data/analysis/m5_active_exit_counterfactual_summary.csv
- data/analysis/m5_active_exit_counterfactual_by_pair.csv
- data/analysis/m15_active_exit_counterfactual_summary.csv
- data/analysis/m15_active_exit_counterfactual_by_pair.csv
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15


@dataclass
class TFConfig:
    label: str
    events_path: str
    module: object
    max_hold: int


CONFIGS = [
    TFConfig("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 500),
    TFConfig("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 500),
]

OUT_DIR = "data/analysis"


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


def _find_active_exit(active: np.ndarray, entry_idx: int, direction: int, max_hold: int) -> tuple[int, float]:
    entry_price = active[entry_idx]
    last_idx = min(entry_idx + max_hold, len(active) - 1)
    for i in range(entry_idx + 1, last_idx + 1):
        pnl = direction * (active[i] - entry_price) * 10000.0
        if pnl <= 0.0:
            return i, pnl
    pnl = direction * (active[last_idx] - entry_price) * 10000.0
    return last_idx, pnl


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
            actual_exit_idx = entry_idx + int(row["duration_bars"])
            if actual_exit_idx >= len(ts):
                continue

            direction = 1 if row["side"] == "LONG" else -1
            active_leg = row["active_leg"]
            active = y if active_leg == "Y" else x

            entry_price = active[entry_idx]
            actual_pnl = direction * (active[actual_exit_idx] - entry_price) * 10000.0

            alt_exit_idx, alt_pnl = _find_active_exit(active, entry_idx, direction, cfg.max_hold)

            rows.append(
                {
                    "pair": pair,
                    "actual_pnl": actual_pnl,
                    "alt_pnl": alt_pnl,
                    "delta_pnl": alt_pnl - actual_pnl,
                    "actual_duration": actual_exit_idx - entry_idx,
                    "alt_duration": alt_exit_idx - entry_idx,
                    "alt_earlier": alt_exit_idx < actual_exit_idx,
                    "alt_later": alt_exit_idx > actual_exit_idx,
                    "actual_positive": actual_pnl > 0,
                    "alt_positive": alt_pnl > 0,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out, out

    summary = pd.DataFrame(
        [
            {
                "trades": len(out),
                "actual_mean": float(out["actual_pnl"].mean()),
                "alt_mean": float(out["alt_pnl"].mean()),
                "delta_mean": float(out["delta_pnl"].mean()),
                "delta_median": float(out["delta_pnl"].median()),
                "alt_better_rate": float((out["alt_pnl"] > out["actual_pnl"]).mean()),
                "alt_worse_rate": float((out["alt_pnl"] < out["actual_pnl"]).mean()),
                "alt_earlier_rate": float(out["alt_earlier"].mean()),
                "alt_later_rate": float(out["alt_later"].mean()),
                "actual_positive_rate": float(out["actual_positive"].mean()),
                "alt_positive_rate": float(out["alt_positive"].mean()),
                "actual_duration_mean": float(out["actual_duration"].mean()),
                "alt_duration_mean": float(out["alt_duration"].mean()),
            }
        ]
    )

    by_pair = out.groupby("pair").agg(
        trades=("pair", "count"),
        actual_mean=("actual_pnl", "mean"),
        alt_mean=("alt_pnl", "mean"),
        delta_mean=("delta_pnl", "mean"),
        alt_better_rate=("alt_pnl", lambda s: (s > out.loc[s.index, "actual_pnl"]).mean()),
        alt_earlier_rate=("alt_earlier", "mean"),
        alt_later_rate=("alt_later", "mean"),
        actual_positive_rate=("actual_positive", "mean"),
        alt_positive_rate=("alt_positive", "mean"),
    ).reset_index()

    return summary, by_pair


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for cfg in CONFIGS:
        summary, by_pair = _analyze(cfg)
        summary_path = os.path.join(OUT_DIR, f"{cfg.label}_active_exit_counterfactual_summary.csv")
        pair_path = os.path.join(OUT_DIR, f"{cfg.label}_active_exit_counterfactual_by_pair.csv")
        summary.to_csv(summary_path, index=False)
        by_pair.to_csv(pair_path, index=False)
        print(f"Saved: {summary_path}")
        print(f"Saved: {pair_path}")


if __name__ == "__main__":
    main()
