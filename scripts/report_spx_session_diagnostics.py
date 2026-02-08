#!/usr/bin/env python3
"""
SPX session diagnostics for two-stage model:
- NY vs non-NY calibration and residuals
- Session-specific threshold sweeps (train-optimized -> test)
- SPX-only model vs baseline model comparison

Outputs CSVs to data/analysis/
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATHS = {
    "m5": "data/meta_model/events_m5_8yr_v3_dual.csv",
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
}
OUT_DIR = "data/analysis"

EDGE_THRESHOLDS = [0, 1, 2, 3, 4, 5, 7, 10]
COST_BPS = 5.0

CLF_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    loss_function="Logloss",
    verbose=False,
    random_seed=42,
)
REG_PARAMS = dict(
    iterations=1200,
    depth=7,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)

CATEGORICAL_FEATURES = ["active_leg", "side"]
NUMERIC_FEATURES = [
    "z_entry",
    "z_velocity",
    "z_lag1",
    "z_lag2",
    "z_lag3",
    "dz_lag1",
    "dz_lag2",
    "spread_std",
    "beta_stability",
    "beta",
    "beta_lag1",
    "beta_lag2",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_1h",
    "ret_Y_1h",
    "ret_X_16b",
    "ret_Y_16b",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

SESSIONS = [
    ("Asia", 0, 7),
    ("London", 7, 13),
    ("New_York", 13, 21),
    ("Late", 21, 24),
]


def _add_sessions(df: pd.DataFrame) -> pd.DataFrame:
    def full_session(h: int) -> str:
        for name, start, end in SESSIONS:
            if start <= h < end:
                return name
        return "Unknown"

    def session_group(h: int) -> str:
        return "New_York" if 13 <= h < 21 else "Non_NY"

    out = df.copy()
    out["session_full"] = out["hour"].map(full_session)
    out["session_group"] = out["hour"].map(session_group)
    return out


def _fit_models(train: pd.DataFrame, test: pd.DataFrame) -> tuple[CatBoostClassifier, CatBoostRegressor, list[str]]:
    use_features = [f for f in FEATURES if f in train.columns]
    cat_idx = [use_features.index(c) for c in CATEGORICAL_FEATURES if c in use_features]

    clf = CatBoostClassifier(**CLF_PARAMS)
    clf.fit(
        Pool(train[use_features], (train["pnl_bps"] > 0).astype(int), cat_features=cat_idx),
        eval_set=Pool(test[use_features], (test["pnl_bps"] > 0).astype(int), cat_features=cat_idx),
        early_stopping_rounds=80,
    )

    reg_pnl = CatBoostRegressor(**REG_PARAMS)
    reg_pnl.fit(
        Pool(train[use_features], train["pnl_bps"], cat_features=cat_idx),
        eval_set=Pool(test[use_features], test["pnl_bps"], cat_features=cat_idx),
        early_stopping_rounds=80,
    )
    return clf, reg_pnl, use_features


def _predict_two_stage(
    df: pd.DataFrame, clf: CatBoostClassifier, reg_pnl: CatBoostRegressor, use_features: list[str]
) -> pd.DataFrame:
    out = df.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    choose_mom = out["p_up"] >= 0.5
    out["chosen_side"] = np.where(choose_mom, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return _add_sessions(out)


def _calibration_bins(df: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for group in ["New_York", "Non_NY"]:
        sub = df[df["session_group"] == group].copy()
        if len(sub) < bins:
            continue
        sub = sub.sort_values("edge_score")
        sub["edge_bin"] = pd.qcut(sub["edge_score"], q=bins, duplicates="drop")
        for bin_label, bucket in sub.groupby("edge_bin", observed=True):
            resid = bucket["chosen_pnl_bps"] - bucket["edge_score"]
            rows.append(
                {
                    "session_group": group,
                    "edge_bin": str(bin_label),
                    "edge_min": float(bucket["edge_score"].min()),
                    "edge_max": float(bucket["edge_score"].max()),
                    "edge_mean": float(bucket["edge_score"].mean()),
                    "pnl_mean": float(bucket["chosen_pnl_bps"].mean()),
                    "win_rate": float((bucket["chosen_pnl_bps"] > 0).mean()),
                    "count": int(len(bucket)),
                    "residual_mean": float(resid.mean()),
                    "residual_std": float(resid.std(ddof=0)),
                }
            )
    return pd.DataFrame(rows)


def _residual_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group in ["New_York", "Non_NY"]:
        sub = df[df["session_group"] == group].copy()
        if sub.empty:
            continue
        resid = sub["chosen_pnl_bps"] - sub["edge_score"]
        rows.append(
            {
                "session_group": group,
                "count": int(len(sub)),
                "resid_mean": float(resid.mean()),
                "resid_median": float(resid.median()),
                "resid_p5": float(resid.quantile(0.05)),
                "resid_p1": float(resid.quantile(0.01)),
                "resid_min": float(resid.min()),
                "resid_max": float(resid.max()),
                "resid_std": float(resid.std(ddof=0)),
                "edge_pnl_corr": float(np.corrcoef(sub["edge_score"], sub["chosen_pnl_bps"])[0, 1])
                if len(sub) > 2
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _threshold_sweep(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for group in ["New_York", "Non_NY"]:
        sub = df[df["session_group"] == group].copy()
        for t in EDGE_THRESHOLDS:
            s = sub[np.abs(sub["edge_score"]) > t]
            pnl = s["chosen_pnl_bps"].to_numpy()
            net = pnl - COST_BPS if len(pnl) else pnl
            rows.append(
                {
                    "session_group": group,
                    "edge_threshold": t,
                    "trades": int(len(s)),
                    "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                    "gross_total_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
                    "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
                    "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _select_thresholds(train_pred: pd.DataFrame) -> dict[str, int]:
    sweep = _threshold_sweep(train_pred)
    best = {}
    for group in ["New_York", "Non_NY"]:
        sub = sweep[sweep["session_group"] == group].copy()
        if sub.empty:
            continue
        # maximize net_total on train
        best_row = sub.loc[sub["net_total_pnl_bps"].idxmax()]
        best[group] = int(best_row["edge_threshold"])
    return best


def _apply_thresholds(test_pred: pd.DataFrame, selected: dict[str, int]) -> pd.DataFrame:
    rows = []
    for group, t in selected.items():
        sub = test_pred[(test_pred["session_group"] == group) & (np.abs(test_pred["edge_score"]) > t)]
        pnl = sub["chosen_pnl_bps"].to_numpy()
        net = pnl - COST_BPS if len(pnl) else pnl
        rows.append(
            {
                "session_group": group,
                "edge_threshold": t,
                "trades": int(len(sub)),
                "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "gross_total_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
                "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
                "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _session_metrics(df: pd.DataFrame, edge_threshold: int, model_label: str) -> pd.DataFrame:
    rows = []
    sub = df[np.abs(df["edge_score"]) > edge_threshold].copy()
    for name, _, _ in SESSIONS:
        ss = sub[sub["session_full"] == name].copy()
        if ss.empty:
            continue
        pnl = ss["chosen_pnl_bps"].to_numpy()
        net = pnl - COST_BPS if len(pnl) else pnl
        rows.append(
            {
                "model": model_label,
                "edge_threshold": edge_threshold,
                "session": name,
                "trades": int(len(ss)),
                "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
                "gross_p5_bps": float(np.quantile(pnl, 0.05)) if len(pnl) else 0.0,
                "gross_p1_bps": float(np.quantile(pnl, 0.01)) if len(pnl) else 0.0,
                "gross_min_bps": float(pnl.min()) if len(pnl) else 0.0,
                "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
                "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=DATA_PATHS.keys(), default="m5")
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    data_path = DATA_PATHS[args.bar]
    df = pl.read_csv(data_path).to_pandas()

    # Use MOM rows only; REV payoff is symmetric (-MOM).
    mom = df[df["strategy_type"] == "MOM"].copy()
    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    clf, reg_abs, use_features = _fit_models(train, test)
    train_pred = _predict_two_stage(train, clf, reg_abs, use_features)
    test_pred = _predict_two_stage(test, clf, reg_abs, use_features)

    # SPX only for diagnostics
    train_spx = train_pred[train_pred["pair"].str.contains("SPX")].copy()
    test_spx = test_pred[test_pred["pair"].str.contains("SPX")].copy()

    # Calibration + residuals (NY vs non-NY)
    calibration = _calibration_bins(test_spx, bins=args.bins)
    residuals = _residual_summary(test_spx)

    calib_out = os.path.join(OUT_DIR, f"spx_{args.bar}_session_calibration.csv")
    resid_out = os.path.join(OUT_DIR, f"spx_{args.bar}_session_residuals.csv")
    calibration.to_csv(calib_out, index=False)
    residuals.to_csv(resid_out, index=False)

    # Threshold sweeps + train-selected thresholds applied to test
    sweep = _threshold_sweep(test_spx)
    sweep_out = os.path.join(OUT_DIR, f"spx_{args.bar}_session_thresholds_holdout.csv")
    sweep.to_csv(sweep_out, index=False)

    selected = _select_thresholds(train_spx)
    applied = _apply_thresholds(test_spx, selected)
    applied_out = os.path.join(OUT_DIR, f"spx_{args.bar}_session_thresholds_selected.csv")
    applied.to_csv(applied_out, index=False)

    # SPX-only model vs baseline
    spx_train_only = train[train["pair"].str.contains("SPX")].copy()
    spx_test_only = test[test["pair"].str.contains("SPX")].copy()
    spx_clf, spx_reg, spx_features = _fit_models(spx_train_only, spx_test_only)
    spx_test_pred = _predict_two_stage(spx_test_only, spx_clf, spx_reg, spx_features)

    session_rows = []
    for edge in [4, 5]:
        session_rows.append(_session_metrics(test_spx, edge, "baseline_all_pairs"))
        session_rows.append(_session_metrics(spx_test_pred, edge, "spx_only"))
    session_compare = pd.concat(session_rows, ignore_index=True)
    session_out = os.path.join(OUT_DIR, f"spx_{args.bar}_session_model_compare.csv")
    session_compare.to_csv(session_out, index=False)

    print(f"Saved:\n- {calib_out}\n- {resid_out}\n- {sweep_out}\n- {applied_out}\n- {session_out}")


if __name__ == "__main__":
    main()
