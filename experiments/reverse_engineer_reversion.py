#!/usr/bin/env python3
"""
Reverse Engineering Reversion (Kalman Only).
Goal: Find a feature inside the Kalman Filter state that predicts Reversion Success vs Failure.
Target: Fade |Z| > 3.0.
Outcome:
- WIN: Reverts to 0 before hitting Stop (6.0).
- LOSS: Hits Stop (6.0) before reverting to 0.

Analysis: Compare distributions of Kalman features (Beta Volatility, Error Variance, Z Velocity) for WIN vs LOSS.
"""

import os
import sys
import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data

# Constants
DATA_DIR = "data/global_1h"
FAST_WINDOW = 100
Z_ENTRY = 3.0
Z_TARGET = 0.0
Z_STOP = 6.0

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close"),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close"),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close"),
]

def analyze_feature(feature_name, values, outcomes):
    """
    Compare average feature value for WIN vs LOSS.
    """
    wins = [v for v, o in zip(values, outcomes) if o == "WIN"]
    losses = [v for v, o in zip(values, outcomes) if o == "LOSS"]
    
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    
    diff = avg_win - avg_loss
    # Normalized diff?
    
    print(f"  {feature_name:<15}: WIN={avg_win:.4f} | LOSS={avg_loss:.4f} | Diff={diff:.4f}")
    if abs(diff) > 0.1 * abs(avg_win): # Significant?
        print(f"    -> POTENTIAL DISCRIMINATOR ({'Higher' if diff > 0 else 'Lower'} in Wins)")

def run_experiment():
    print(f"--- REVERSE ENGINEERING REVERSION (Window={FAST_WINDOW}) ---")
    
    all_features = {
        "beta_vol": [],
        "error_vol": [],
        "z_velocity": [],
        "beta_slope": [],
        "z_accel": []
    }
    all_outcomes = []
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Kalman States
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        # Features Preparation
        beta_series = pd.Series(betas)
        error_series = pd.Series(errors)
        z_series = pd.Series(z_scores)
        
        # Beta Volatility (24h)
        beta_vol = beta_series.rolling(24).std().fillna(0).to_numpy()
        
        # Error Volatility (24h)
        error_vol = error_series.rolling(24).std().fillna(0).to_numpy()
        
        # Z Velocity (5 bars)
        z_vel = z_series.diff(5).abs().fillna(0).to_numpy() # Speed of move
        
        # Beta Slope (24h) - Simple diff for speed
        beta_slope = beta_series.diff(24).abs().fillna(0).to_numpy()
        
        # Z Acceleration
        z_accel = z_series.diff(1).diff(1).abs().fillna(0).to_numpy()
        
        # 2. Iterate Events
        last_entry = 0
        min_gap = 20
        
        pair_wins = 0
        pair_losses = 0
        
        for i in range(200, len(y)-200):
            z = z_scores[i]
            
            if abs(z) < Z_ENTRY: continue
            if i - last_entry < min_gap: continue
            
            # Identify Outcome
            outcome = "UNKNOWN"
            
            # Forward scan
            found = False
            for j in range(i+1, min(i+500, len(y))):
                z_fut = z_scores[j]
                
                # Check Win (Cross 0)
                if (z > 0 and z_fut <= 0) or (z < 0 and z_fut >= 0):
                    outcome = "WIN"
                    found = True
                    break
                    
                # Check Loss (Hit Stop)
                if abs(z_fut) >= Z_STOP:
                    outcome = "LOSS"
                    found = True
                    break
            
            if not found: continue # Timed out / No result
            
            # Save Feature Values at Entry (i)
            # Normalize some features by current error_vol or similar?
            # Start with raw values.
            
            all_features["beta_vol"].append(beta_vol[i])
            all_features["error_vol"].append(error_vol[i])
            all_features["z_velocity"].append(z_vel[i])
            all_features["beta_slope"].append(beta_slope[i])
            all_features["z_accel"].append(z_accel[i])
            
            all_outcomes.append(outcome)
            
            if outcome == "WIN": pair_wins += 1
            else: pair_losses += 1
            
            last_entry = i
            
        print(f"  Trades: {pair_wins + pair_losses} (Wins: {pair_wins}, Losses: {pair_losses})")

    print("\n--- AGGREGATE FEATURE ANALYSIS ---")
    print(f"Total Samples: {len(all_outcomes)} (Wins: {all_outcomes.count('WIN')}, Losses: {all_outcomes.count('LOSS')})")
    
    for name, values in all_features.items():
        analyze_feature(name, values, all_outcomes)

if __name__ == "__main__":
    run_experiment()
