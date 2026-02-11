#!/usr/bin/env python3
"""
Exit attribution analysis for MOM trades.
Quantifies how often non-active leg move dominates active leg move at exit.

Outputs:
- data/analysis/m5_exit_attribution_summary.csv
- data/analysis/m5_exit_attribution_by_pair.csv
- data/analysis/m15_exit_attribution_summary.csv
- data/analysis/m15_exit_attribution_by_pair.csv
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


CONFIGS = [
    TFConfig("m5", "data/events/events_m5_8yr_v3_mom.csv", m5),
    TFConfig("m15", "data/events/events_m15_8yr_v3_mom.csv", m15),
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


def _analyze(cfg: TFConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(
        cfg.events_path,
        usecols=["pair", "timestamp", "active_leg", "side", "duration_bars", "pnl_bps"],
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
            other = x if active_leg == "Y" else y

            active_move = direction * (active[exit_idx] - active[entry_idx]) * 10000.0
            other_move = direction * (other[exit_idx] - other[entry_idx]) * 10000.0
            ratio = abs(other_move) / (abs(active_move) + abs(other_move) + 1e-12)
            dominant = abs(other_move) > abs(active_move)

            pnl_bps = float(row["pnl_bps"])
            pnl_gap = abs(active_move - pnl_bps)

            rows.append(
                {
                    "pair": pair,
                    "active_leg": active_leg,
                    "active_move": active_move,
                    "other_move": other_move,
                    "ratio_other": ratio,
                    "other_dominant": dominant,
                    "pnl_gap": pnl_gap,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out, out

    summary = pd.DataFrame(
        [
            {
                "trades": len(out),
                "other_dominant_rate": float(out["other_dominant"].mean()),
                "ratio_other_mean": float(out["ratio_other"].mean()),
                "ratio_other_p50": float(out["ratio_other"].median()),
                "ratio_other_p80": float(out["ratio_other"].quantile(0.8)),
                "ratio_other_gt_0_6": float((out["ratio_other"] > 0.6).mean()),
                "pnl_gap_mean": float(out["pnl_gap"].mean()),
                "pnl_gap_p95": float(out["pnl_gap"].quantile(0.95)),
            }
        ]
    )

    by_pair = out.groupby("pair").agg(
        trades=("pair", "count"),
        other_dominant_rate=("other_dominant", "mean"),
        ratio_other_mean=("ratio_other", "mean"),
        ratio_other_p50=("ratio_other", "median"),
        ratio_other_p80=("ratio_other", lambda s: s.quantile(0.8)),
        ratio_other_gt_0_6=("ratio_other", lambda s: (s > 0.6).mean()),
    ).reset_index()

    return summary, by_pair


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for cfg in CONFIGS:
        summary, by_pair = _analyze(cfg)
        summary_path = os.path.join(OUT_DIR, f"{cfg.label}_exit_attribution_summary.csv")
        pair_path = os.path.join(OUT_DIR, f"{cfg.label}_exit_attribution_by_pair.csv")
        summary.to_csv(summary_path, index=False)
        by_pair.to_csv(pair_path, index=False)
        print(f"Saved: {summary_path}")
        print(f"Saved: {pair_path}")


if __name__ == "__main__":
    main()
