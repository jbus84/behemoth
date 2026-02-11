#!/usr/bin/env python3
"""
Guardrail sensitivity under smoothing and slippage.

Smoothing: compute guardrail skip-rate vs noguard using existing smoothing impact outputs.
Slippage: apply proportional slippage to PnL and recompute guardrail metrics.

Outputs:
- data/analysis/<bar>_guardrail_smoothing_skiprate.csv
- data/analysis/<bar>_guardrail_slippage_sensitivity.csv
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "src"))
from behemoth.core.guardrail import apply_loss_streak_guardrail
from behemoth.core.metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 7
PROP_SLIP = [0.0, 0.02, 0.05, 0.1]

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
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
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
    return apply_loss_streak_guardrail(
        df,
        loss_threshold=0.0,
        loss_streak=LOSS_STREAK,
        cooldown_days=COOLDOWN_DAYS,
    )


def _smoothing_skiprate(bar: str) -> pd.DataFrame:
    path = os.path.join(OUT_DIR, f"{bar}_smoothing_strategy_impact.csv")
    df = pd.read_csv(path)
    pivot = df.pivot_table(
        index=["pair", "config"],
        columns="guardrail",
        values="base_trades",
        aggfunc="sum",
    ).reset_index()
    if "guard" not in pivot.columns or "noguard" not in pivot.columns:
        return pd.DataFrame()
    pivot["skip_rate"] = 1.0 - (pivot["guard"] / pivot["noguard"].replace(0, np.nan))
    pivot["skip_rate"] = pivot["skip_rate"].fillna(0.0)
    return pivot.rename(columns={"guard": "guard_trades", "noguard": "noguard_trades"})


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)

    # Smoothing skip rates
    for label, _, _ in CONFIGS:
        smooth = _smoothing_skiprate(label)
        if not smooth.empty:
            smooth.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_smoothing_skiprate.csv"), index=False)
            print(f"Saved: {OUT_DIR}/{label}_guardrail_smoothing_skiprate.csv")

    # Slippage sensitivity
    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        rows = []
        for slip in PROP_SLIP:
            adj = df.copy()
            pnl = adj["pnl_bps"].to_numpy()
            adj["pnl_bps"] = pnl - slip * np.abs(pnl)

            base = _metrics(adj)
            guard = _metrics(_apply_guardrail(adj))
            rows.append({"slip_prop": slip, "guardrail": False, **base})
            rows.append({"slip_prop": slip, "guardrail": True, **guard})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_slippage_sensitivity.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_guardrail_slippage_sensitivity.csv")


if __name__ == "__main__":
    main()
