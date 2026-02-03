#!/usr/bin/env python3
"""
5-Minute (M5) Meta Model Assessment
Target: Regression (Predict PnL in bps)
"""

import polars as pl
import numpy as np
import os
from catboost import CatBoostRegressor, Pool

DATA_PATH = "data/meta_model/events_m5_8yr_v3_dual.csv"

CATEGORICAL_FEATURES = ['strategy_type', 'active_leg', 'side']
NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

def assess_5m():
    if not os.path.exists(DATA_PATH):
        print(f"Data not found: {DATA_PATH}")
        return

    print("Loading 5M Data...")
    df = pl.read_csv(DATA_PATH)
    
    # Train/Test Split (Same Year Logic)
    # Train 2018-2023, Test 2024-2025
    train_df = df.filter(pl.col('year') <= 2023)
    test_df = df.filter(pl.col('year') >= 2024)
    
    print(f"Train: {len(train_df)} events")
    print(f"Test:  {len(test_df)} events")
    
    if len(train_df) == 0:
        print("No training data found (check year column).")
        return

    X_train = train_df.select(ALL_FEATURES).to_pandas()
    y_train = train_df['pnl_bps'].to_numpy()
    
    X_test = test_df.select(ALL_FEATURES).to_pandas()
    pnl_test = test_df['pnl_bps'].to_numpy()
    
    cat_indices = [X_train.columns.get_loc(c) for c in CATEGORICAL_FEATURES]
    
    print("\nTraining CatBoost (M5)...")
    model = CatBoostRegressor(
        iterations=500, # Faster for assessment
        depth=6,
        learning_rate=0.05,
        loss_function='RMSE',
        verbose=False,
        random_seed=42
    )
    
    model.fit(Pool(X_train, y_train, cat_features=cat_indices))
    
    print("\n--- 5M RESULTS (2024-2025) ---")
    y_pred = model.predict(X_test)
    
    print("\n| Pred > | Trades | Win Rate | Mean PnL | Total PnL |")
    print("|--------|--------|----------|----------|-----------|")
    
    for thresh in [0, 10, 20]:
        mask = y_pred > thresh
        if mask.sum() > 0:
            n = mask.sum()
            wr = 100 * np.mean(pnl_test[mask] > 0)
            mean_pnl = np.mean(pnl_test[mask])
            total_pnl = np.sum(pnl_test[mask])
            
            print(f"| {thresh:>6} | {n:>6} | {wr:>7.1f}% | {mean_pnl:>8.2f} | {total_pnl:>9.0f} |")

if __name__ == "__main__":
    assess_5m()
