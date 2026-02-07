#!/usr/bin/env python3
"""
Apply ML filter (CatBoost reg) on top of MOM loss-streak guardrail (M15).

Outputs:
- data/analysis/mom_guardrail_ml_sweep.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

DATA_PATH = "data/meta_model/events_m15_8yr_v3_mom.csv"
MODEL_PATH = "models/meta_model_m15/catboost_m15_reg.cbm"
OUT_DIR = "data/analysis"

LOSS_STREAK = 3
COOLDOWN_DAYS = 14
THRESHOLDS = [0, 5, 10, 15, 20]


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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = df["timestamp"].astype("int64")
    df["exit_ts"] = df["timestamp"] + (df["duration_bars"].astype(int) * 15 * 60 * 1_000_000_000)

    # Load model + build predictions
    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    feature_names = list(getattr(model, "feature_names_", []))
    if not feature_names:
        raise RuntimeError("Model feature names are missing.")

    # Backfill legacy 4h features from 16-bar returns if needed
    if "ret_X_4h" in feature_names and "ret_X_4h" not in df.columns and "ret_X_16b" in df.columns:
        df["ret_X_4h"] = df["ret_X_16b"]
    if "ret_Y_4h" in feature_names and "ret_Y_4h" not in df.columns and "ret_Y_16b" in df.columns:
        df["ret_Y_4h"] = df["ret_Y_16b"]

    missing = [f for f in feature_names if f not in df.columns]
    if missing:
        raise RuntimeError(f"Missing features in dataset: {missing}")

    df["pred_pnl"] = model.predict(df[feature_names])

    # Baseline vs guardrail
    base = df.sort_values("exit_ts").copy()
    guard = _apply_guardrail(df)

    rows = []
    for label, sub in [("baseline", base), ("guardrail", guard)]:
        for t in THRESHOLDS:
            filt = sub[sub["pred_pnl"] >= t].copy()
            stats = _metrics(filt)
            rows.append(
                {
                    "variant": label,
                    "pred_threshold": t,
                    **stats,
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "mom_guardrail_ml_sweep.csv"), index=False)
    print("Saved: data/analysis/mom_guardrail_ml_sweep.csv")


if __name__ == "__main__":
    main()
