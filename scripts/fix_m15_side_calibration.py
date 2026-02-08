#!/usr/bin/env python3
"""
Fix M15 side-selection bias by calibrating predictions per strategy type.

Why this exists:
- Raw predictions are not on a comparable scale between MOM and REV.
- Using one raw threshold (e.g. pred > 20) starves REV.

Fix:
- Fit calibration on TRAIN predictions per strategy_type:
  score_z = (pred - mean_type) / std_type
- At each event (pair,timestamp), choose side with higher score_z
- Gate on score_z > z_threshold (not raw pred threshold)
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

DATA_PATH = "data/meta_model/events_m15_8yr_v3_dual.csv"
MODEL_PATH = "models/meta_model_m15/catboost_m15_reg.cbm"
OUT_DIR = "data/analysis"
CALIB_PATH = "models/meta_model_m15/side_calibration_m15.json"

FEATURES = [
    "strategy_type",
    "active_leg",
    "side",
    "z_entry",
    "z_velocity",
    "spread_std",
    "beta_stability",
    "beta",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_4h",
    "ret_Y_4h",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]

Z_THRESHOLDS = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
COSTS_BPS = [3, 5, 9]


def _stats_rows(selected: pd.DataFrame, z_threshold: float, cost_bps: int) -> dict[str, float | int]:
    pnl = selected["chosen_pnl_bps"].to_numpy()
    n = len(selected)
    gross_wr = float((pnl > 0).mean() * 100.0) if n else 0.0
    gross_mean = float(pnl.mean()) if n else 0.0
    gross_total = float(pnl.sum()) if n else 0.0

    net = pnl - cost_bps if n else pnl
    net_wr = float((net > 0).mean() * 100.0) if n else 0.0
    net_mean = float(net.mean()) if n else 0.0
    net_total = float(net.sum()) if n else 0.0

    rev_mask = selected["chosen_side"] == "REV"
    rev_trades = int(rev_mask.sum())
    mom_trades = int((~rev_mask).sum())

    return {
        "z_threshold": z_threshold,
        "cost_bps": cost_bps,
        "trades": n,
        "mom_trades": mom_trades,
        "rev_trades": rev_trades,
        "rev_share_pct": float(rev_trades / n * 100.0) if n else 0.0,
        "gross_win_rate_pct": gross_wr,
        "gross_mean_pnl_bps": gross_mean,
        "gross_total_pnl_bps": gross_total,
        "net_win_rate_pct": net_wr,
        "net_mean_pnl_bps": net_mean,
        "net_total_pnl_bps": net_total,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CALIB_PATH), exist_ok=True)

    df = pl.read_csv(DATA_PATH).to_pandas()
    train = df[df["year"] <= 2023].copy()
    test = df[df["year"] >= 2024].copy()

    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)

    model_features = list(getattr(model, "feature_names_", [])) or [f for f in FEATURES if f in train.columns]
    train["pred_pnl"] = model.predict(train[model_features])
    test["pred_pnl"] = model.predict(test[model_features])

    # Fit calibration on train predictions by type
    calib = (
        train.groupby("strategy_type")["pred_pnl"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "mu", "std": "sigma"})
    )
    # Guard against degenerate sigma
    calib["sigma"] = calib["sigma"].replace(0.0, 1.0)

    with open(CALIB_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "MOM": {"mu": float(calib.loc["MOM", "mu"]), "sigma": float(calib.loc["MOM", "sigma"])},
                "REV": {"mu": float(calib.loc["REV", "mu"]), "sigma": float(calib.loc["REV", "sigma"])},
            },
            f,
            indent=2,
        )

    # Apply z-score normalization by strategy type
    test["score_z"] = np.nan
    for st in ["MOM", "REV"]:
        mu = float(calib.loc[st, "mu"])
        sigma = float(calib.loc[st, "sigma"])
        m = test["strategy_type"] == st
        test.loc[m, "score_z"] = (test.loc[m, "pred_pnl"] - mu) / sigma

    # Pair MOM/REV rows for event-level decision
    mom = test[test["strategy_type"] == "MOM"][
        ["pair", "timestamp", "pnl_bps", "pred_pnl", "score_z"]
    ].rename(columns={"pnl_bps": "pnl_mom", "pred_pnl": "pred_mom", "score_z": "z_mom"})
    rev = test[test["strategy_type"] == "REV"][
        ["pair", "timestamp", "pnl_bps", "pred_pnl", "score_z"]
    ].rename(columns={"pnl_bps": "pnl_rev", "pred_pnl": "pred_rev", "score_z": "z_rev"})
    paired = mom.merge(rev, on=["pair", "timestamp"], how="inner")

    # Keep baseline table too (legacy raw >20, best of two)
    legacy = test.loc[test.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()].copy()
    legacy = legacy[legacy["pred_pnl"] > 20.0].copy()
    legacy["chosen_side"] = legacy["strategy_type"]
    legacy["chosen_pnl_bps"] = legacy["pnl_bps"]

    rows: list[dict[str, float | int | str]] = []

    # Legacy rows for comparison
    for cost in COSTS_BPS:
        r = _stats_rows(legacy, z_threshold=-1.0, cost_bps=cost)
        r["mode"] = "legacy_raw_pred_gt_20"
        rows.append(r)

    # Calibrated rows
    for zt in Z_THRESHOLDS:
        choose_mom = paired["z_mom"] >= paired["z_rev"]
        chosen_z = np.where(choose_mom, paired["z_mom"], paired["z_rev"])
        chosen_side = np.where(choose_mom, "MOM", "REV")
        chosen_pnl = np.where(choose_mom, paired["pnl_mom"], paired["pnl_rev"])

        selected = paired.copy()
        selected["chosen_side"] = chosen_side
        selected["chosen_pnl_bps"] = chosen_pnl
        selected["chosen_z"] = chosen_z
        selected = selected[selected["chosen_z"] > zt].copy()

        for cost in COSTS_BPS:
            r = _stats_rows(selected, z_threshold=zt, cost_bps=cost)
            r["mode"] = "calibrated_z"
            rows.append(r)

    out_df = pd.DataFrame(rows).sort_values(["mode", "z_threshold", "cost_bps"])
    out_path = os.path.join(OUT_DIR, "m15_calibrated_side_selection.csv")
    out_df.to_csv(out_path, index=False)

    # Compact console view at cost=5
    view = out_df[out_df["cost_bps"] == 5][
        [
            "mode",
            "z_threshold",
            "trades",
            "rev_share_pct",
            "gross_win_rate_pct",
            "gross_mean_pnl_bps",
            "net_win_rate_pct",
            "net_mean_pnl_bps",
            "net_total_pnl_bps",
        ]
    ]
    print("\nM15 side-selection comparison (cost=5bps):")
    print(view.to_string(index=False))
    print(f"\nSaved:\n- {out_path}\n- {CALIB_PATH}")


if __name__ == "__main__":
    main()
