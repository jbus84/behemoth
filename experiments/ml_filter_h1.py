"""
ML Filter Experiment (H1) with CatBoost.
Performs Walk-Forward Optimization (WFO) to train a filter model.
Goal: Filter out low-quality trades BEFORE they hit the guardrail.
"""

import pandas as pd
import numpy as np
import polars as pl
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import roc_auc_score, precision_score, recall_score
import matplotlib.pyplot as plt
import os

FEATURE_PATH = "data/ml/features_h1_wide.parquet"
OUTPUT_DIR = "data/ml/results_h1"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_experiment():
    print("--- ML FILTER WFO (H1) ---")
    
    # 1. Load Data
    df = pl.read_parquet(FEATURE_PATH).to_pandas()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    
    print(f"Loaded {len(df)} events.")
    
    # 2. Define Features & Target
    # Stricter Target: Profitable Trade (> 10 bps to cover some costs)
    df["target"] = (df["pnl_bps"] > 10).astype(int)
    
    excludes = ["timestamp", "pair", "strategy_type", "active_leg", "side", "outcome", "pnl_bps", "duration_bars", "rolling_win_rate_10", "rolling_avg_pnl_10", "year", "target"]
    feature_cols = [c for c in df.columns if c not in excludes]
    cat_features = ["pair", "strategy_type", "side"] # 'active_leg' might be redundant or useful
    
    # Ensure categorical columns are strings
    for c in cat_features:
        if c in df.columns:
            df[c] = df[c].astype(str)

    # Correct Feature List: Numeric + Categorical
    numeric_feats = [c for c in df.columns if c.startswith("z_") or c.startswith("beta_") or c.startswith("vol_")]
    final_features = numeric_feats + cat_features
    
    print(f"Features: {len(final_features)}")
    
    # 3. WFO Loop (Annual)
    years = sorted(df["year"].unique())
    print(f"Years: {years}")
    
    all_predictions = [] 
    
    start_train_year = years[0]
    first_test_year = years[3] # 4th year (e.g. 2021 if start 2018)
    
    # Define Categorical Features Indices
    cat_features_indices = [final_features.index(c) for c in cat_features if c in final_features]
    
    for test_year in years:
        if test_year < first_test_year:
            continue
            
        print(f"\nDistilling Alpha for {test_year}...")
        
        # Train: All years BEFORE test_year
        train_mask = df["year"] < test_year
        test_mask = df["year"] == test_year
        
        X_train_full = df.loc[train_mask, final_features]
        y_train_full = df.loc[train_mask, "target"]
        
        X_test = df.loc[test_mask, final_features]
        y_test = df.loc[test_mask, "target"]
        
        if len(X_test) == 0:
            continue
            
        # Split Train into Train/Val for Early Stopping
        split_idx = int(len(X_train_full) * 0.8)
        X_train, X_val = X_train_full.iloc[:split_idx], X_train_full.iloc[split_idx:]
        y_train, y_val = y_train_full.iloc[:split_idx], y_train_full.iloc[split_idx:]
        
        train_pool = Pool(X_train, y_train, cat_features=cat_features_indices)
        val_pool = Pool(X_val, y_val, cat_features=cat_features_indices)
        test_pool = Pool(X_test, cat_features=cat_features_indices)
        
        # Init Model
        model = CatBoostClassifier(
            iterations=500,
            learning_rate=0.03,
            depth=6,
            loss_function='Logloss',
            verbose=False,
            early_stopping_rounds=50
        )

        # Fit
        model.fit(
            train_pool,
            eval_set=val_pool,
            early_stopping_rounds=50,
            verbose=False
        )
        
        # Predict
        probs = model.predict_proba(test_pool)[:, 1]
        
        # Store Results
        subset = df.loc[test_mask].copy()
        subset["proba"] = probs
        all_predictions.append(subset)
        
        try:
            score = roc_auc_score(y_test, probs)
            print(f"  Test AUC: {score:.4f} | Size: {len(X_test)}")
        except:
            print(f"  Test AUC: N/A | Size: {len(X_test)}")
    # 4. Compile Results
    if not all_predictions:
        print("No predictions generated.")
        return

    df_res = pd.concat(all_predictions)

    # 5. Determine Threshold (Optimize for Sharpe)
    best_sharpe = -np.inf
    best_thresh = 0.5
    
    thresholds = np.linspace(0.4, 0.7, 31)
    
    print("\n--- Threshold Optimization (Sharpe) ---")
    for t in thresholds:
        mask = df_res["proba"] >= t
        if mask.sum() < 50: continue
        
        subset_pnl = df_res.loc[mask, "pnl_bps"]
        mean_pnl = subset_pnl.mean()
        std_pnl = subset_pnl.std()
        
        if std_pnl == 0: continue
        
        # Annualized Sharpe Approximation (assuming H1 bars, but these are trades)
        # Just use detailed sharpe: mean / std * sqrt(Trades/Year?)
        # Simple metric: mean / std
        sharpe = mean_pnl / std_pnl
        
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_thresh = t
            
    print(f"Best Threshold: {best_thresh:.2f} | Sharpe: {best_sharpe:.4f}")
    
    # Apply Best Threshold
    df_res["accepted"] = df_res["proba"] >= best_thresh
    
    # Save CSV for Benchmark ingestion
    # We only need to save the accepted trades? 
    # Or save all with a flag?
    # For benchmark_guardrail, we can feed it the FILTERED CSV.
    
    df_filtered = df_res[df_res["accepted"]].copy()
    out_csv = os.path.join(OUTPUT_DIR, "events_h1_ml_filtered.csv")
    df_filtered.to_csv(out_csv, index=False)
    
    print(f"\nSaved {len(df_filtered)} filtered trades to {out_csv}")
    # Save ALL predictions for analysis
    out_csv_full = os.path.join(OUTPUT_DIR, "events_h1_ml_full.csv")
    df_res.to_csv(out_csv_full, index=False)
    
    # Analysis of Accepted vs Rejected
    accepted = df_res[df_res["accepted"]]
    rejected = df_res[~df_res["accepted"]]
    
    print(f"\n--- Analysis ---")
    print(f"Total PnL (Accepted): {accepted['pnl_bps'].sum():.1f} bps | Count: {len(accepted)}")
    print(f"Total PnL (Rejected): {rejected['pnl_bps'].sum():.1f} bps | Count: {len(rejected)}")
    
    # Win Rates
    wr_acc = (accepted['pnl_bps'] > 0).mean()
    wr_rej = (rejected['pnl_bps'] > 0).mean()
    print(f"Win Rate (Accepted): {wr_acc:.1%}")
    print(f"Win Rate (Rejected): {wr_rej:.1%}")
    
    # Big Winners (> 50 bps) Recall
    big_winners = df_res[df_res["pnl_bps"] > 50]
    caught_winners = big_winners[big_winners["accepted"]]
    recall_big = len(caught_winners) / len(big_winners) if len(big_winners) > 0 else 0
    print(f"Big Winners in Data (>50bps): {len(big_winners)}")
    print(f"Big Winners Caught: {len(caught_winners)} ({recall_big:.1%})")
    
    # Average PnL
    print(f"Avg PnL (Accepted): {accepted['pnl_bps'].mean():.2f}")
    print(f"Avg PnL (Rejected): {rejected['pnl_bps'].mean():.2f}")

    # Save Filtered for Benchmark
    df_filtered = accepted.copy()

if __name__ == "__main__":
    run_experiment()
