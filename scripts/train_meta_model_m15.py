#!/usr/bin/env python3
"""
M15 Meta Model Training and Holdout Reporting
Target: Regression (predict pnl_bps)

Reports:
1) Overall holdout metrics (2024-2025)
2) Threshold stats (overall)
3) Threshold stats by strategy_type (MOM / REV)
4) Event-level best-of-two (pick max pred per pair,timestamp), plus type split
"""

from __future__ import annotations

import os
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_m15_8yr_v3_dual.csv"
MODEL_DIR = "models/meta_model_m15"
ANALYSIS_DIR = "data/analysis"

CATEGORICAL_FEATURES = ["strategy_type", "active_leg", "side"]
NUMERIC_FEATURES = [
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
    "ret_X_16b",
    "ret_Y_16b",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

THRESHOLDS = [0, 10, 15, 20, 25, 30]

MODEL_PARAMS = dict(
    iterations=1000,
    depth=6,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    mae = float(np.mean(np.abs(y_pred - y_true)))
    if len(y_true) > 1 and np.std(y_true) > 0 and np.std(y_pred) > 0:
        corr = float(np.corrcoef(y_pred, y_true)[0, 1])
    else:
        corr = 0.0
    sign_acc = float(np.mean((y_pred * y_true) > 0))
    return {"rmse": rmse, "mae": mae, "corr": corr, "sign_acc": sign_acc}


def _threshold_rows(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    thresholds: Iterable[int],
    prefix: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    prefix = prefix or {}
    for t in thresholds:
        mask = y_pred > t
        n = int(mask.sum())
        if n > 0:
            wr = float(np.mean(y_true[mask] > 0) * 100.0)
            mean_pnl = float(np.mean(y_true[mask]))
            total_pnl = float(np.sum(y_true[mask]))
        else:
            wr = 0.0
            mean_pnl = 0.0
            total_pnl = 0.0
        rows.append(
            {
                **prefix,
                "pred_threshold": t,
                "trades": n,
                "win_rate_pct": wr,
                "mean_pnl_bps": mean_pnl,
                "total_pnl_bps": total_pnl,
            }
        )
    return rows


def _event_level_rows(df_test: pd.DataFrame, thresholds: Iterable[int]) -> pd.DataFrame:
    idx = df_test.groupby(["pair", "timestamp"])["pred_pnl"].idxmax()
    best = df_test.loc[idx].copy()
    rows: list[dict[str, object]] = []
    for t in thresholds:
        sub = best[best["pred_pnl"] > t]
        y = sub["pnl_bps"].to_numpy()
        mom = sub[sub["strategy_type"] == "MOM"]
        rev = sub[sub["strategy_type"] == "REV"]
        rows.append(
            {
                "pred_threshold": t,
                "trades": len(sub),
                "win_rate_pct": float((y > 0).mean() * 100.0) if len(y) else 0.0,
                "mean_pnl_bps": float(y.mean()) if len(y) else 0.0,
                "total_pnl_bps": float(y.sum()) if len(y) else 0.0,
                "mom_count": len(mom),
                "mom_win_rate_pct": float((mom["pnl_bps"] > 0).mean() * 100.0) if len(mom) else 0.0,
                "mom_mean_pnl_bps": float(mom["pnl_bps"].mean()) if len(mom) else 0.0,
                "rev_count": len(rev),
                "rev_win_rate_pct": float((rev["pnl_bps"] > 0).mean() * 100.0) if len(rev) else 0.0,
                "rev_mean_pnl_bps": float(rev["pnl_bps"].mean()) if len(rev) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(ANALYSIS_DIR, exist_ok=True)

    print(f"Loading data: {DATA_PATH}")
    df = pl.read_csv(DATA_PATH)

    train_df = df.filter(pl.col("year") <= 2023)
    test_df = df.filter(pl.col("year") >= 2024)

    print(f"Train rows (2018-2023): {len(train_df)}")
    print(f"Test rows  (2024-2025): {len(test_df)}")

    use_features = [f for f in ALL_FEATURES if f in train_df.columns]
    missing = [f for f in ALL_FEATURES if f not in use_features]
    if missing:
        print(f"Missing features skipped: {missing}")

    X_train = train_df.select(use_features).to_pandas()
    y_train = train_df["pnl_bps"].to_numpy()

    X_test = test_df.select(use_features).to_pandas()
    y_test = test_df["pnl_bps"].to_numpy()

    cat_indices = [X_train.columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in use_features]
    model = CatBoostRegressor(**MODEL_PARAMS)
    model.fit(
        Pool(X_train, y_train, cat_features=cat_indices),
        eval_set=Pool(X_test, y_test, cat_features=cat_indices),
        early_stopping_rounds=50,
    )

    model_path = os.path.join(MODEL_DIR, "catboost_m15_reg.cbm")
    model.save_model(model_path)
    print(f"Saved model: {model_path}")

    y_pred = model.predict(X_test)
    overall = _metrics(y_test, y_pred)
    overall_df = pd.DataFrame([overall])
    overall_path = os.path.join(ANALYSIS_DIR, "m15_holdout_overall_metrics.csv")
    overall_df.to_csv(overall_path, index=False)

    thresh_overall = pd.DataFrame(_threshold_rows(y_test, y_pred, THRESHOLDS))
    thresh_overall_path = os.path.join(ANALYSIS_DIR, "m15_holdout_thresholds_overall.csv")
    thresh_overall.to_csv(thresh_overall_path, index=False)

    test_pd = test_df.to_pandas()
    test_pd["pred_pnl"] = y_pred

    by_type_rows: list[dict[str, object]] = []
    for strategy_type, sub in test_pd.groupby("strategy_type"):
        stats = _metrics(sub["pnl_bps"].to_numpy(), sub["pred_pnl"].to_numpy())
        stats["strategy_type"] = strategy_type
        stats["rows"] = len(sub)
        by_type_rows.append(stats)

    by_type_metrics = pd.DataFrame(by_type_rows).sort_values("strategy_type")
    by_type_metrics_path = os.path.join(ANALYSIS_DIR, "m15_holdout_metrics_by_type.csv")
    by_type_metrics.to_csv(by_type_metrics_path, index=False)

    by_type_thresh_rows: list[dict[str, object]] = []
    for strategy_type, sub in test_pd.groupby("strategy_type"):
        by_type_thresh_rows.extend(
            _threshold_rows(
                sub["pnl_bps"].to_numpy(),
                sub["pred_pnl"].to_numpy(),
                THRESHOLDS,
                prefix={"strategy_type": strategy_type},
            )
        )
    by_type_thresh = pd.DataFrame(by_type_thresh_rows).sort_values(["strategy_type", "pred_threshold"])
    by_type_thresh_path = os.path.join(ANALYSIS_DIR, "m15_holdout_thresholds_by_type.csv")
    by_type_thresh.to_csv(by_type_thresh_path, index=False)

    event_level = _event_level_rows(test_pd, THRESHOLDS)
    event_level_path = os.path.join(ANALYSIS_DIR, "m15_holdout_event_level_thresholds.csv")
    event_level.to_csv(event_level_path, index=False)

    fi = sorted(zip(use_features, model.get_feature_importance()), key=lambda x: -x[1])

    print("\n=== Overall Holdout Metrics (2024-2025) ===")
    print(overall_df.to_string(index=False))

    print("\n=== Threshold Stats (Overall) ===")
    print(thresh_overall.to_string(index=False))

    print("\n=== Metrics By Type (MOM / REV) ===")
    print(by_type_metrics.to_string(index=False))

    print("\n=== Threshold Stats By Type (MOM / REV) ===")
    print(by_type_thresh.to_string(index=False))

    print("\n=== Event-Level Best-Of-Two Threshold Stats ===")
    print(event_level.to_string(index=False))

    print("\n=== Top 10 Features ===")
    for name, score in fi[:10]:
        print(f"{name}: {score:.2f}")

    print("\nSaved reports:")
    print(f"- {overall_path}")
    print(f"- {thresh_overall_path}")
    print(f"- {by_type_metrics_path}")
    print(f"- {by_type_thresh_path}")
    print(f"- {event_level_path}")


if __name__ == "__main__":
    main()
