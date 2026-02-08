#!/usr/bin/env python3
"""
Generate holdout predictions and plot MOM-only edge_score vs realized PnL.
Outputs:
- data/analysis/m5_two_stage_holdout_predictions.csv
- data/analysis/m15_two_stage_holdout_predictions.csv
- docs/figures/edge_vs_pnl_holdout_t4.png
- docs/figures/edge_vs_pnl_holdout_t5.png
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import matplotlib.pyplot as plt
from catboost import CatBoostClassifier, CatBoostRegressor, Pool


DATA = {
    "m5": "data/meta_model/events_m5_8yr_v3_dual.csv",
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
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


def _fit_predict(path: str) -> pd.DataFrame:
    df = pl.read_csv(path).to_pandas()
    mom = df[df["strategy_type"] == "MOM"].copy()
    train = mom[mom["year"] <= 2023].copy()
    test = mom[mom["year"] >= 2024].copy()

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

    out = test.copy()
    out["p_up"] = clf.predict_proba(out[use_features])[:, 1]
    out["pred_pnl"] = reg_pnl.predict(out[use_features])
    choose_mom = out["p_up"] >= 0.5
    out["chosen_side"] = np.where(choose_mom, "MOM", "REV")
    out["chosen_pnl_bps"] = np.where(choose_mom, out["pnl_bps"], -out["pnl_bps"])
    out["edge_score"] = out["pred_pnl"]
    return out


def _plot_panel(ax, df: pd.DataFrame, title: str, threshold: float) -> None:
    # MOM-only: trade when p_up >= 0.5 and edge_score > threshold.
    mom = df[(df["p_up"] >= 0.5) & (df["edge_score"] > threshold)].copy()
    x = mom["edge_score"].to_numpy()
    y = mom["chosen_pnl_bps"].to_numpy()
    # Clip for visualization
    x_lim = np.quantile(np.abs(x), 0.995)
    y_lim = np.quantile(np.abs(y), 0.995)
    x_clip = np.clip(x, -x_lim, x_lim)
    y_clip = np.clip(y, -y_lim, y_lim)

    hb = ax.hexbin(x_clip, y_clip, gridsize=45, cmap="viridis", mincnt=1)
    ax.axhline(0, color="#374151", lw=0.8)
    ax.axvline(0, color="#374151", lw=0.8)
    ax.set_title(title)
    ax.set_xlabel("edge_score")
    ax.set_ylabel("realized pnl (bps)")
    return hb


def main() -> None:
    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = Path("docs/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)

    m5_pred = _fit_predict(DATA["m5"])
    m15_pred = _fit_predict(DATA["m15"])

    m5_path = out_dir / "m5_two_stage_holdout_predictions.csv"
    m15_path = out_dir / "m15_two_stage_holdout_predictions.csv"
    m5_pred.to_csv(m5_path, index=False)
    m15_pred.to_csv(m15_path, index=False)

    for threshold in (4, 5):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
        _plot_panel(
            axes[0],
            m5_pred,
            f"M5 Holdout: Edge vs Realized PnL (edge>{threshold})",
            threshold,
        )
        _plot_panel(
            axes[1],
            m15_pred,
            f"M15 Holdout: Edge vs Realized PnL (edge>{threshold})",
            threshold,
        )
        fig.tight_layout()
        fig.savefig(fig_dir / f"edge_vs_pnl_holdout_t{threshold}.png", dpi=200)


if __name__ == "__main__":
    main()
