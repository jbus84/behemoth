#!/usr/bin/env python3
"""
Apply cap on concurrent trades sharing the same underlying leg.
Simple rule: at most 1 trade per underlying leg active at a time.
Outputs:
- data/analysis/m5_shared_leg_cap_metrics.csv
- data/analysis/m15_shared_leg_cap_metrics.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade
import build_meta_dataset_v3_m5 as m5
import build_meta_dataset_v3 as m15

OUT_DIR = "data/analysis"

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv", m5, 5),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv", m15, 15),
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


def _pair_map(module):
    return {name: (fx, fy) for name, fx, fy, *_ in module.PAIRS}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, module, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        pair_legs = _pair_map(module)

        base = df.sort_values("exit_ts")

        active = []
        kept = []
        open_by_leg = defaultdict(int)

        for row in base.itertuples(index=False):
            # cleanup expired
            now = int(row.timestamp)
            active = [t for t in active if t[1] > now]
            open_by_leg = defaultdict(int)
            for _, end_ts, legs in active:
                for leg in legs:
                    open_by_leg[leg] += 1

            legs = pair_legs.get(row.pair)
            if legs is None:
                continue
            if open_by_leg[legs[0]] > 0 or open_by_leg[legs[1]] > 0:
                continue

            kept.append(row._asdict())
            active.append((row.timestamp, row.exit_ts, legs))

        capped = pd.DataFrame(kept)

        out = pd.DataFrame([
            {"variant": "baseline", **_metrics(base)},
            {"variant": "shared_leg_cap_1", **_metrics(capped)},
        ])

        out.to_csv(os.path.join(OUT_DIR, f"{label}_shared_leg_cap_metrics.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_shared_leg_cap_metrics.csv")


if __name__ == "__main__":
    main()
