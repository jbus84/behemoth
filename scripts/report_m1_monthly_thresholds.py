#!/usr/bin/env python3
"""
Monthly threshold breakdown for M1 models (gross PnL only).
Defaults to low thresholds to avoid sparse high-threshold stats.
"""

from __future__ import annotations

import argparse
import os
from typing import Iterable

import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

DATA_PATH = "data/meta_model/events_m1_8yr_v3_dual.csv"
ANALYSIS_DIR = "data/analysis"


def _parse_thresholds(text: str) -> list[float]:
    vals = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(float(part))
    return vals


def _threshold_rows(df: pd.DataFrame, thresholds: Iterable[float]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for t in thresholds:
        sub = df[df["pred_pnl"] > t]
        n = len(sub)
        if n:
            wr = float((sub["pnl_bps"] > 0).mean() * 100.0)
            mean_pnl = float(sub["pnl_bps"].mean())
            total_pnl = float(sub["pnl_bps"].sum())
        else:
            wr = 0.0
            mean_pnl = 0.0
            total_pnl = 0.0
        rows.append(
            {
                "pred_threshold": t,
                "trades": n,
                "gross_win_rate_pct": wr,
                "gross_mean_bps": mean_pnl,
                "gross_total_bps": total_pnl,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly threshold breakdown for M1 models")
    parser.add_argument("--profile", choices=["m5", "m15"], default="m5")
    parser.add_argument("--data-path", default=DATA_PATH)
    parser.add_argument("--model-path", default="")
    parser.add_argument("--thresholds", default="0,1,2,3,4,5")
    parser.add_argument("--analysis-dir", default=ANALYSIS_DIR)
    args = parser.parse_args()

    os.makedirs(args.analysis_dir, exist_ok=True)

    if not args.model_path:
        suffix = "m5style" if args.profile == "m5" else "m15style"
        args.model_path = f"models/meta_model_m1/catboost_m1_reg_{suffix}.cbm"

    thresholds = _parse_thresholds(args.thresholds)

    print(f"Loading data: {args.data_path}")
    df = pl.read_csv(args.data_path)
    holdout = df.filter(pl.col("year") >= 2024)

    if len(holdout) == 0:
        raise SystemExit("No holdout rows (year >= 2024).")

    model = CatBoostRegressor()
    model.load_model(args.model_path)

    holdout_pd = holdout.to_pandas()
    features = model.feature_names_ or [c for c in holdout_pd.columns if c not in {"pnl_bps"}]
    X = holdout_pd[features]
    holdout_pd["pred_pnl"] = model.predict(X)

    holdout_pd["timestamp"] = pd.to_datetime(holdout_pd["timestamp"], errors="coerce")
    holdout_pd = holdout_pd.dropna(subset=["timestamp"])
    holdout_pd["month"] = holdout_pd["timestamp"].dt.strftime("%Y-%m")

    # Best-of-two per event (pair,timestamp)
    idx = holdout_pd.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()
    best = holdout_pd.loc[idx].copy()

    rows: list[dict[str, object]] = []
    for month, sub in best.groupby("month"):
        for row in _threshold_rows(sub, thresholds):
            rows.append({"month": month, **row})

    out_path = os.path.join(args.analysis_dir, f"m1_monthly_thresholds_{args.profile}.csv")
    pd.DataFrame(rows).sort_values(["month", "pred_threshold"]).to_csv(out_path, index=False)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
