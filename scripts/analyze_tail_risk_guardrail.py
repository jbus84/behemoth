#!/usr/bin/env python3
"""
Tail-risk guardrail: pause pair if extreme frequency exceeds threshold
within rolling window.
Extreme = |pnl_bps| beyond 99.9th percentile of entire dataset.
Outputs:
- data/analysis/m5_tail_risk_guardrail.csv
- data/analysis/m15_tail_risk_guardrail.csv
"""

from __future__ import annotations

import os
import sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
WINDOW_TRADES = 50
THRESHOLDS = [0.1, 0.2, 0.3]  # fraction of extremes in window
COOLDOWN_TRADES = 20

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv"),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv"),
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


def apply_tail_guardrail(df: pd.DataFrame, extreme_threshold: float, frac_threshold: float) -> pd.DataFrame:
    df = df.sort_values("timestamp").copy()
    df["extreme"] = df["pnl_bps"].abs() >= extreme_threshold

    kept = []
    state = {}
    for row in df.itertuples(index=False):
        pair = row.pair
        if pair not in state:
            state[pair] = {"window": [], "pause": 0}
        st = state[pair]

        # pause countdown
        if st["pause"] > 0:
            st["pause"] -= 1
            continue

        # update window
        st["window"].append(1 if row.extreme else 0)
        if len(st["window"]) > WINDOW_TRADES:
            st["window"].pop(0)

        if len(st["window"]) == WINDOW_TRADES:
            frac = sum(st["window"]) / WINDOW_TRADES
            if frac >= frac_threshold:
                st["pause"] = COOLDOWN_TRADES
                st["window"] = []
                continue

        kept.append(row)

    return pd.DataFrame(kept)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in CONFIGS:
        df = pd.read_csv(path, usecols=["pair", "timestamp", "pnl_bps"])
        q_hi = df["pnl_bps"].quantile(0.999)
        extreme_threshold = float(max(abs(q_hi), abs(df["pnl_bps"].quantile(0.001))))

        rows = []
        rows.append({"variant": "baseline", **_metrics(df), "threshold": 0.0})

        for frac in THRESHOLDS:
            filtered = apply_tail_guardrail(df, extreme_threshold, frac)
            rows.append({"variant": f"tail_guardrail_{int(frac*100)}", **_metrics(filtered), "threshold": frac})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_tail_risk_guardrail.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_tail_risk_guardrail.csv")


if __name__ == "__main__":
    main()
