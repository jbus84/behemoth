#!/usr/bin/env python3
"""
REV reversion-probability classifier:
- Target: outcome == WIN_REV (z0 cross before stop/timeout)
- Evaluate holdout PnL when filtering by predicted win probability
- Sweep REV entry thresholds (abs(z_entry) >= t)

Outputs:
- data/analysis/<bar>_rev_reversion_prob_sweep.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier, Pool

DATA_PATHS = {
    "m30": "data/meta_model/events_m30_8yr_v3_dual.csv",
    "h1": "data/meta_model/events_h1_8yr_v3_dual.csv",
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
    "ret_X_4h",
    "ret_Y_4h",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

ENTRY_THRESHOLDS = [2.5, 3.0, 3.5, 4.0, 4.5]
PROB_THRESHOLDS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75]

CLF_PARAMS = dict(
    iterations=800,
    depth=6,
    learning_rate=0.05,
    loss_function="Logloss",
    verbose=False,
    random_seed=42,
)


def _fit_classifier(train: pd.DataFrame, test: pd.DataFrame) -> tuple[CatBoostClassifier, list[str]]:
    use_features = [f for f in FEATURES if f in train.columns]
    cat_idx = [train[use_features].columns.get_loc(c) for c in CATEGORICAL_FEATURES if c in use_features]

    clf = CatBoostClassifier(**CLF_PARAMS)
    clf.fit(
        Pool(train[use_features], train["label_win_rev"], cat_features=cat_idx),
        eval_set=Pool(test[use_features], test["label_win_rev"], cat_features=cat_idx),
        early_stopping_rounds=60,
    )
    return clf, use_features


def _metrics(pnl: np.ndarray) -> dict[str, float]:
    if len(pnl) == 0:
        return {
            "trades": 0,
            "win_rate_pct": 0.0,
            "mean_pnl_bps": 0.0,
            "total_pnl_bps": 0.0,
        }
    return {
        "trades": int(len(pnl)),
        "win_rate_pct": float((pnl > 0).mean() * 100.0),
        "mean_pnl_bps": float(pnl.mean()),
        "total_pnl_bps": float(pnl.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m30", "h1"], default="m30")
    args = parser.parse_args()

    out_dir = Path("data/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.bar}_rev_reversion_prob_sweep.csv"

    df = pl.read_csv(DATA_PATHS[args.bar]).to_pandas()
    rev = df[df["strategy_type"] == "REV"].copy()
    rev["label_win_rev"] = (rev["outcome"] == "WIN_REV").astype(int)

    rows = []
    for entry_t in ENTRY_THRESHOLDS:
        filt = rev[np.abs(rev["z_entry"]) >= entry_t].copy()
        train = filt[filt["year"] <= 2023].copy()
        test = filt[filt["year"] >= 2024].copy()
        if len(train) < 2000 or len(test) < 200:
            rows.append(
                {
                    "entry_threshold": entry_t,
                    "prob_threshold": np.nan,
                    "note": "insufficient_samples",
                    **_metrics(np.array([])),
                }
            )
            continue

        clf, use_features = _fit_classifier(train, test)
        test = test.copy()
        test["p_win_rev"] = clf.predict_proba(test[use_features])[:, 1]

        # Baseline (no prob filter)
        base = _metrics(test["pnl_bps"].to_numpy())
        rows.append(
            {
                "entry_threshold": entry_t,
                "prob_threshold": 0.0,
                "note": "no_filter",
                **base,
            }
        )

        for p in PROB_THRESHOLDS:
            sub = test[test["p_win_rev"] >= p]
            stats = _metrics(sub["pnl_bps"].to_numpy())
            rows.append(
                {
                    "entry_threshold": entry_t,
                    "prob_threshold": p,
                    "note": "",
                    **stats,
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
