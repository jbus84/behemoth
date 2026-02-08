#!/usr/bin/env python3
"""
Viability diagnostics for two-stage single-strategy models (MOM or REV).

Outputs per timeframe:
- data/analysis/<bar>_two_stage_holdout_predictions.csv
- data/analysis/<bar>_viability_monthly.csv
- data/analysis/<bar>_viability_session.csv
- data/analysis/<bar>_viability_symbol.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATA_PATHS = {
    "m5": "data/meta_model/events_m5_8yr_v3_dual.csv",
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
    "h1": "data/meta_model/events_h1_8yr_v3_dual.csv",
    "h2": "data/meta_model/events_h2_8yr_v3_dual.csv",
    "m30": "data/meta_model/events_m30_8yr_v3_dual.csv",
}

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

EDGE_THRESHOLDS = [0, 1, 2, 3, 4, 5]

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

    out = df.copy()
    out["session"] = out["hour"].map(full_session)
    return out


def _fit_models(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[CatBoostClassifier, CatBoostRegressor, list[str]]:
    use_features = [f for f in FEATURES if f in train.columns]
    cat_idx = [train[use_features].columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in use_features]

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


def _predict(
    df: pd.DataFrame, clf: CatBoostClassifier, reg_pnl: CatBoostRegressor, use_features: list[str]
) -> pd.DataFrame:
    out = df.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    out["chosen_pnl_bps"] = out["pnl_bps"]
    out["edge_score"] = out["pred_pnl"]
    return out


def _aggregate(df: pd.DataFrame, group_cols: list[str], cost_bps: float) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for key, sub in df.groupby(group_cols):
        if not isinstance(key, tuple):
            key = (key,)
        group_values = dict(zip(group_cols, key))
        for t in EDGE_THRESHOLDS:
            filt = sub[(sub["edge_score"] > t) & (sub["p_up"] >= 0.5)]
            pnl = filt["chosen_pnl_bps"].to_numpy()
            n = len(pnl)
            if n:
                gross_wr = float((pnl > 0).mean() * 100.0)
                gross_mean = float(pnl.mean())
                gross_total = float(pnl.sum())
                net = pnl - cost_bps
                net_wr = float((net > 0).mean() * 100.0)
                net_mean = float(net.mean())
                net_total = float(net.sum())
            else:
                gross_wr = gross_mean = gross_total = 0.0
                net_wr = net_mean = net_total = 0.0
            row = {
                **group_values,
                "edge_threshold": t,
                "trades": n,
                "gross_win_rate_pct": gross_wr,
                "gross_mean_pnl_bps": gross_mean,
                "gross_total_pnl_bps": gross_total,
                "net_win_rate_pct": net_wr,
                "net_mean_pnl_bps": net_mean,
                "net_total_pnl_bps": net_total,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m5", "m15", "h1", "h2", "m30"], default="m5")
    parser.add_argument("--strategy", choices=["MOM", "REV"], default="MOM")
    parser.add_argument("--cost", type=float, default=0.0)
    args = parser.parse_args()

    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pl.read_csv(DATA_PATHS[args.bar]).to_pandas()
    data = df[df["strategy_type"] == args.strategy].copy()
    train = data[data["year"] <= 2023].copy()
    test = data[data["year"] >= 2024].copy()

    clf, reg_pnl, use_features = _fit_models(train, test)
    pred = _predict(test, clf, reg_pnl, use_features)
    pred["timestamp"] = pd.to_datetime(pred["timestamp"], errors="coerce")
    pred = pred.dropna(subset=["timestamp"])
    pred["month"] = pred["timestamp"].dt.strftime("%Y-%m")
    pred = _add_sessions(pred)

    suffix = args.strategy.lower()
    pred_path = out_dir / f"{args.bar}_two_stage_holdout_predictions_{suffix}.csv"
    pred.to_csv(pred_path, index=False)
    # Backwards-compatible path (overwritten each run)
    pred_legacy = out_dir / f"{args.bar}_two_stage_holdout_predictions.csv"
    pred.to_csv(pred_legacy, index=False)

    monthly = _aggregate(pred, ["month"], args.cost).sort_values(["month", "edge_threshold"])
    monthly_path = out_dir / f"{args.bar}_viability_monthly_{suffix}.csv"
    monthly.to_csv(monthly_path, index=False)
    monthly_legacy = out_dir / f"{args.bar}_viability_monthly.csv"
    monthly.to_csv(monthly_legacy, index=False)

    session = _aggregate(pred, ["session"], args.cost).sort_values(["session", "edge_threshold"])
    session_path = out_dir / f"{args.bar}_viability_session_{suffix}.csv"
    session.to_csv(session_path, index=False)
    session_legacy = out_dir / f"{args.bar}_viability_session.csv"
    session.to_csv(session_legacy, index=False)

    symbol = _aggregate(pred, ["pair"], args.cost).sort_values(["pair", "edge_threshold"])
    symbol_path = out_dir / f"{args.bar}_viability_symbol_{suffix}.csv"
    symbol.to_csv(symbol_path, index=False)
    symbol_legacy = out_dir / f"{args.bar}_viability_symbol.csv"
    symbol.to_csv(symbol_legacy, index=False)

    print(
        "Saved:"
        f"\n- {pred_path}"
        f"\n- {monthly_path}"
        f"\n- {session_path}"
        f"\n- {symbol_path}"
        f"\nStrategy: {args.strategy}, Cost: {args.cost} bps"
    )


if __name__ == "__main__":
    main()
