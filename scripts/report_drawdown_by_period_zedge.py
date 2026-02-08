#!/usr/bin/env python3
"""
Compute drawdown by year and month for MOM trades using z-scored edge.
Edge_z is computed from training-only pred_pnl stats (no leakage).
Cost-free. Outputs per-timeframe CSVs with DD reduction vs edge_z>0 baseline.
"""

from __future__ import annotations

import os
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

DATASETS = {
    "M15": "data/meta_model/events_m15_8yr_v3_dual.csv",
    "M30": "data/meta_model/events_m30_8yr_v3_dual.csv",
    "M45": "data/meta_model/events_m45_8yr_v3_dual.csv",
    "H1": "data/meta_model/events_h1_8yr_v3_dual.csv",
}

OUT_DIR = "data/analysis"
Z_THRESHOLDS = [0, 1, 2, 3, 4, 5]

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
    "ret_X_4h",
    "ret_Y_4h",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

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
    return out


def _max_drawdown(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return float(dd.min())


def _calc_period_dd(df: pd.DataFrame, period: str) -> pd.DataFrame:
    rows = []
    for zt in Z_THRESHOLDS:
        sub = df[(df["edge_z"] > zt) & (df["p_up"] >= 0.5)].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("timestamp")
        for key, grp in sub.groupby(period):
            pnl = grp["pnl_bps"].to_numpy()
            rows.append(
                {
                    "period": key,
                    "edge_z": zt,
                    "trades": int(len(pnl)),
                    "total_pnl_bps": float(pnl.sum()),
                    "max_drawdown_bps": _max_drawdown(pnl),
                }
            )
    return pd.DataFrame(rows)


def _add_reduction(df: pd.DataFrame) -> pd.DataFrame:
    base = df[df["edge_z"] == 0].set_index("period")
    out_rows = []
    for _, row in df.iterrows():
        period = row["period"]
        base_dd = base.loc[period, "max_drawdown_bps"] if period in base.index else 0.0
        dd = row["max_drawdown_bps"]
        if base_dd == 0:
            reduction_pct = 0.0
        else:
            reduction_pct = 1.0 - (abs(dd) / abs(base_dd))
        out_rows.append(
            {
                **row.to_dict(),
                "baseline_dd_bps": float(base_dd),
                "dd_reduction_bps": float(dd - base_dd),
                "dd_reduction_pct": float(reduction_pct),
            }
        )
    return pd.DataFrame(out_rows)


def _prepare_time_fields(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df["ts"] = ts
    df["year"] = df["ts"].dt.year
    df["month"] = df["ts"].dt.strftime("%Y-%m")
    return df


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path in DATASETS.items():
        df = pl.read_csv(path).to_pandas()
        df = df[df["strategy_type"] == "MOM"].copy()
        df = _prepare_time_fields(df)

        train = df[df["year"] <= 2023].copy()
        test = df[df["year"] >= 2024].copy()
        if test.empty:
            continue

        clf, reg_pnl, use_features = _fit_models(train, test)
        train_pred = _predict(train, clf, reg_pnl, use_features)
        test_pred = _predict(test, clf, reg_pnl, use_features)

        mu = float(train_pred["pred_pnl"].mean())
        sigma = float(train_pred["pred_pnl"].std(ddof=0))
        if sigma <= 1e-9:
            sigma = 1.0
        test_pred["edge_z"] = (test_pred["pred_pnl"] - mu) / sigma

        year_dd = _calc_period_dd(test_pred, "year")
        month_dd = _calc_period_dd(test_pred, "month")
        if year_dd.empty or month_dd.empty:
            continue

        year_dd = _add_reduction(year_dd).sort_values(["period", "edge_z"])
        month_dd = _add_reduction(month_dd).sort_values(["period", "edge_z"])

        year_out = os.path.join(OUT_DIR, f"drawdown_year_zedge_{label.lower()}.csv")
        month_out = os.path.join(OUT_DIR, f"drawdown_month_zedge_{label.lower()}.csv")
        year_dd.to_csv(year_out, index=False)
        month_dd.to_csv(month_out, index=False)

        print(f"\n{label} z-edge drawdown saved:")
        print(f"- {year_out}")
        print(f"- {month_out}")


if __name__ == "__main__":
    main()
