#!/usr/bin/env python3
"""
REV-gated two-stage exploration:
- Use standard two-stage model (trained on MOM rows).
- Allow MOM trades if |edge| > t_mom.
- Allow REV trades only if p_up <= gate AND |edge| > t_rev.
Select (t_mom, t_rev, gate) on train (<=2023) to maximize net total at 5 bps.

Outputs (per bar size):
- data/analysis/<bar>_rev_gate_holdout_selected.csv
- data/analysis/<bar>_rev_gate_wfo_selected.csv
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

EDGE_THRESHOLDS_MOM = [0, 1, 2, 3, 4, 5, 7, 10]
EDGE_THRESHOLDS_REV = [0, 1, 2, 3, 4, 5, 7, 10]
GATES = [0.45, 0.40, 0.35, 0.30, 0.25]

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
    df: pd.DataFrame, clf: CatBoostClassifier, reg_abs: CatBoostRegressor, use_features: list[str]
) -> pd.DataFrame:
    out = df.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    choose_mom = out["p_up"] >= 0.5
    out["chosen_side"] = np.where(choose_mom, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return out


def _apply_gate(df: pd.DataFrame, t_mom: int, t_rev: int, gate: float) -> pd.DataFrame:
    mom_mask = (df["chosen_side"] == "MOM") & (np.abs(df["edge_score"]) > t_mom)
    rev_mask = (df["chosen_side"] == "REV") & (df["p_up"] <= gate) & (np.abs(df["edge_score"]) > t_rev)
    return df[mom_mask | rev_mask].copy()


def _score(df: pd.DataFrame, cost: int = 5) -> dict[str, float | int]:
    pnl = df["chosen_pnl_bps"].to_numpy()
    net = pnl - cost if len(pnl) else pnl
    return {
        "trades": len(df),
        "rev_share_pct": float((df["chosen_side"] == "REV").mean() * 100.0) if len(df) else 0.0,
        "gross_mean_pnl_bps": float(pnl.mean()) if len(pnl) else 0.0,
        "gross_total_pnl_bps": float(pnl.sum()) if len(pnl) else 0.0,
        "net_mean_pnl_bps": float(net.mean()) if len(net) else 0.0,
        "net_total_pnl_bps": float(net.sum()) if len(net) else 0.0,
    }


def _select_best(train_pred: pd.DataFrame, cost: int = 5) -> tuple[int, int, float]:
    best = (EDGE_THRESHOLDS_MOM[0], EDGE_THRESHOLDS_REV[0], GATES[0])
    best_net = -np.inf
    for t_mom in EDGE_THRESHOLDS_MOM:
        for t_rev in EDGE_THRESHOLDS_REV:
            for gate in GATES:
                sub = _apply_gate(train_pred, t_mom, t_rev, gate)
                net_total = _score(sub, cost=cost)["net_total_pnl_bps"]
                if net_total > best_net:
                    best_net = net_total
                    best = (t_mom, t_rev, gate)
    return best


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m5", "m15"], default="m5")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    df = pl.read_csv(DATA_PATHS[args.bar]).to_pandas()
    mom = df[df["strategy_type"] == "MOM"].copy()

    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

    clf, reg_abs, use_features = _fit_models(train, test)
    train_pred = _predict(train, clf, reg_abs, use_features)
    test_pred = _predict(test, clf, reg_abs, use_features)

    t_mom, t_rev, gate = _select_best(train_pred, cost=5)
    holdout = _apply_gate(test_pred, t_mom, t_rev, gate)
    metrics = _score(holdout, cost=5)

    holdout_out = os.path.join(OUT_DIR, f"{args.bar}_rev_gate_holdout_selected.csv")
    pd.DataFrame(
        [
            {
                "t_mom": t_mom,
                "t_rev": t_rev,
                "gate": gate,
                **metrics,
            }
        ]
    ).to_csv(holdout_out, index=False)

    # WFO with per-fold selection
    wfo_rows = []
    for year in [2022, 2023, 2024, 2025]:
        tr = mom[mom["year"] < year].copy()
        te = mom[mom["year"] == year].copy()
        if len(tr) < 10000 or len(te) < 1000:
            continue
        clf_y, reg_y, feat_y = _fit_models(tr, te)
        tr_pred = _predict(tr, clf_y, reg_y, feat_y)
        te_pred = _predict(te, clf_y, reg_y, feat_y)
        t_m, t_r, g = _select_best(tr_pred, cost=5)
        filt = _apply_gate(te_pred, t_m, t_r, g)
        row = {"test_year": year, "t_mom": t_m, "t_rev": t_r, "gate": g, **_score(filt, cost=5)}
        wfo_rows.append(row)

    wfo_out = os.path.join(OUT_DIR, f"{args.bar}_rev_gate_wfo_selected.csv")
    pd.DataFrame(wfo_rows).to_csv(wfo_out, index=False)

    print(f"{args.bar.upper()} REV-gate holdout (cost=5bps):")
    print(pd.read_csv(holdout_out).to_string(index=False))
    print(f"\nSaved:\n- {holdout_out}\n- {wfo_out}")


if __name__ == "__main__":
    main()
