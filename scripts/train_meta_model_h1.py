#!/usr/bin/env python3
"""
H1 Meta Model Training (Final Configuration)
Target: Regression (Predict PnL in bps)
Filter: Predict > 20 bps
"""

import polars as pl
import numpy as np
import os
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"
MODEL_DIR = "models/meta_model_h1"
os.makedirs(MODEL_DIR, exist_ok=True)
WFO_DIR = "data/meta_model/wfo_results"
os.makedirs(WFO_DIR, exist_ok=True)

CATEGORICAL_FEATURES = ['strategy_type', 'active_leg', 'side']
NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

MODEL_PARAMS = dict(
    iterations=1000,
    depth=6,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=100,
    random_seed=42
)


def _compute_metrics(y_true, y_pred, threshold=20.0):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
    mae = float(np.mean(np.abs(y_pred - y_true)))
    if len(y_true) > 1 and np.std(y_true) > 0 and np.std(y_pred) > 0:
        corr = float(np.corrcoef(y_pred, y_true)[0, 1])
    else:
        corr = 0.0

    sign_acc = float(np.mean((y_pred * y_true) > 0))
    mask = y_pred > threshold
    n = int(mask.sum())
    if n > 0:
        win_rate = float(np.mean(y_true[mask] > 0))
        mean_pnl = float(np.mean(y_true[mask]))
        total_pnl = float(np.sum(y_true[mask]))
    else:
        win_rate = 0.0
        mean_pnl = 0.0
        total_pnl = 0.0

    return {
        "rmse": rmse,
        "mae": mae,
        "corr": corr,
        "sign_acc": sign_acc,
        "trades_gt_thresh": n,
        "win_rate_gt_thresh": win_rate,
        "mean_pnl_gt_thresh": mean_pnl,
        "total_pnl_gt_thresh": total_pnl,
    }


def _fit_model(X_train, y_train, X_val, y_val):
    cat_indices = [X_train.columns.get_loc(c) for c in CATEGORICAL_FEATURES]
    model = CatBoostRegressor(**MODEL_PARAMS)
    model.fit(
        Pool(X_train, y_train, cat_features=cat_indices),
        eval_set=Pool(X_val, y_val, cat_features=cat_indices),
        early_stopping_rounds=50,
    )
    return model


def run_wfo(df, start_test_year=2022, end_test_year=2025, threshold=20.0):
    print("\n--- WALK-FORWARD EVALUATION (EXPANDING WINDOW) ---")
    rows = []

    for test_year in range(start_test_year, end_test_year + 1):
        train_df = df.filter(pl.col("year") < test_year)
        test_df = df.filter(pl.col("year") == test_year)

        if len(train_df) < 1000 or len(test_df) < 100:
            print(f"Skipping {test_year}: insufficient data.")
            continue

        X_train = train_df.select(ALL_FEATURES).to_pandas()
        y_train = train_df["pnl_bps"].to_numpy()

        X_test = test_df.select(ALL_FEATURES).to_pandas()
        y_test = test_df["pnl_bps"].to_numpy()

        print(f"\nFold {test_year}: Train {train_df['year'].min()}-{test_year-1} | Test {test_year}")
        model = _fit_model(X_train, y_train, X_test, y_test)
        y_pred = model.predict(X_test)

        metrics = _compute_metrics(y_test, y_pred, threshold=threshold)
        rows.append({
            "test_year": test_year,
            "train_start": int(train_df["year"].min()),
            "train_end": test_year - 1,
            "n_train": len(train_df),
            "n_test": len(test_df),
            **metrics,
        })

        print(f"  RMSE: {metrics['rmse']:.2f} | MAE: {metrics['mae']:.2f} | Corr: {metrics['corr']:.3f} | "
              f"SignAcc: {metrics['sign_acc']:.3f} | Trades>th: {metrics['trades_gt_thresh']}")

    if rows:
        out_path = os.path.join(WFO_DIR, "h1_wfo_summary.csv")
        pl.DataFrame(rows).write_csv(out_path)
        print(f"\nWFO summary saved to {out_path}")
    else:
        print("No WFO folds produced.")


def train_and_evaluate(df):
    # Final holdout (static) for reference only
    train_df = df.filter(pl.col("year") <= 2023)
    test_df = df.filter(pl.col("year") >= 2024)

    print(f"\nTrain: {len(train_df)} events (2018-2023)")
    print(f"Test:  {len(test_df)} events (2024-2025)")

    X_train = train_df.select(ALL_FEATURES).to_pandas()
    y_train = train_df["pnl_bps"].to_numpy()

    X_test = test_df.select(ALL_FEATURES).to_pandas()
    pnl_test = test_df["pnl_bps"].to_numpy()

    print("\nTraining CatBoost Regressor...")
    model = _fit_model(X_train, y_train, X_test, pnl_test)

    # Save model
    model_path = f"{MODEL_DIR}/catboost_h1_reg.cbm"
    model.save_model(model_path)
    print(f"\nModel saved to {model_path}")

    # Evaluation
    print("\n--- FINAL EVALUATION (2024-2025) ---")
    y_pred = model.predict(X_test)

    # Threshold Analysis
    print("\n| Pred > | Trades | Win Rate | Mean PnL | Total PnL |")
    print("|--------|--------|----------|----------|-----------|")

    for thresh in [0, 10, 15, 20, 25, 30]:
        mask = y_pred > thresh
        if mask.sum() > 0:
            n = mask.sum()
            wr = 100 * np.mean(pnl_test[mask] > 0)
            mean_pnl = np.mean(pnl_test[mask])
            total_pnl = np.sum(pnl_test[mask])

            print(f"| {thresh:>6} | {n:>6} | {wr:>7.1f}% | {mean_pnl:>8.2f} | {total_pnl:>9.0f} |")

    # Feature Importance
    print("\n--- Top Features ---")
    imp = sorted(zip(ALL_FEATURES, model.get_feature_importance()), key=lambda x: -x[1])
    for f, v in imp[:10]:
        print(f"{f}: {v:.1f}")

if __name__ == "__main__":
    print("Loading H1 Data...")
    df = pl.read_csv(DATA_PATH)
    run_wfo(df)
    train_and_evaluate(df)
