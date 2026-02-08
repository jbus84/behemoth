#!/usr/bin/env python3
"""
Test pair-specific cap: remove pairs with extreme tail imbalance.
Criterion: extreme_mean_loss magnitude exceeds extreme_mean_win by X bps.
Outputs:
- data/analysis/m5_extreme_pair_cap_metrics.csv
- data/analysis/m15_extreme_pair_cap_metrics.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
THRESHOLDS = [50, 100, 150, 200]

CONFIGS = [
    ("m5", "data/meta_model/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/meta_model/events_m15_8yr_v3_mom.csv"),
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
    ts = df["timestamp"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "pnl_bps"])
        q_hi = df["pnl_bps"].quantile(0.999)
        q_lo = df["pnl_bps"].quantile(0.001)
        extreme = df[(df["pnl_bps"] >= q_hi) | (df["pnl_bps"] <= q_lo)].copy()

        agg = extreme.groupby("pair").agg(
            extreme_mean_win=("pnl_bps", lambda s: s[s > 0].mean() if (s > 0).any() else 0.0),
            extreme_mean_loss=("pnl_bps", lambda s: s[s <= 0].mean() if (s <= 0).any() else 0.0),
        ).reset_index()
        agg["loss_bias"] = agg["extreme_mean_loss"].abs() - agg["extreme_mean_win"].abs()

        rows = []
        base = _metrics(df)
        rows.append({"variant": "baseline", **base, "removed_pairs": 0, "threshold": 0})

        for thr in THRESHOLDS:
            bad_pairs = set(agg[agg["loss_bias"] > thr]["pair"])
            filtered = df[~df["pair"].isin(bad_pairs)]
            metrics = _metrics(filtered)
            rows.append({"variant": f"cap_loss_bias_{thr}", **metrics, "removed_pairs": len(bad_pairs), "threshold": thr})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_extreme_pair_cap_metrics.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_extreme_pair_cap_metrics.csv")


if __name__ == "__main__":
    main()
