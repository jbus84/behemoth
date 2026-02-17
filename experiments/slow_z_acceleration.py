#!/usr/bin/env python3
"""
Slow-Z Acceleration Filter Experiment.
Hypothesis: Deceleration predicts Reversion even on Slow Timeframes (Window=750).
Filter: Fade |Z_750| > 3.0 ONLY if Z-Acceleration (Change in Velocity) < THRESH.
Note: Slow Z moves slower, so Acceleration thresholds must be smaller.
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
from behemoth.core.events import simulate_trade

# Constants
DATA_DIR = "data/global_1h"
SLOW_WINDOW = 750
Z_ENTRY_REV = 3.0
Z_STOP_LEVEL = 6.0 # Standard Stop
THRESHOLDS = [0.05, 0.1, 0.2, 0.5]

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close"),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close"),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close"),
]

def run_experiment():
    print(f"--- SLOW-Z ACCELERATION FLITER (Window={SLOW_WINDOW}) ---")
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Slow Kalman States
        betas, errors, _ = compute_kalman_states(y, x, window=SLOW_WINDOW)
        z_scores = compute_z_scores(errors, window=SLOW_WINDOW)
        
        # 2. Compute Z-Acceleration
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()
        
        # Baseline (No Filter)
        base_trades = 0
        base_pnl = 0
        last_entry = 0
        min_gap = 20
        
        # Pre-calc Baseline
        for i in range(SLOW_WINDOW, len(y)-200):
            z = z_scores[i]
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            if z > 0: dir = -1
            else: dir = 1
            active_asset = "Y"
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            base_trades += 1
            base_pnl += pnl
            last_entry = i
            
        avg = base_pnl / base_trades if base_trades > 0 else 0
        print(f"  BASELINE: {base_trades} trades, {base_pnl:.0f} bps ({avg:.1f} avg)")
        
        # Filtered Tests
        for thresh in THRESHOLDS:
            f_trades = 0
            f_pnl = 0
            last_entry = 0
            
            for i in range(SLOW_WINDOW, len(y)-200):
                z = z_scores[i]
                acc = z_accel[i]
                
                if abs(z) < Z_ENTRY_REV: continue
                if i - last_entry < min_gap: continue
                if acc >= thresh: continue # Filter strictly
                
                if z > 0: dir = -1
                else: dir = 1
                active_asset = "Y"
                
                pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
                f_trades += 1
                f_pnl += pnl
                last_entry = i
                
            f_avg = f_pnl / f_trades if f_trades > 0 else 0
            print(f"  [Accel<{thresh}] {f_trades} trades, {f_pnl:.0f} bps ({f_avg:.1f} avg)")

if __name__ == "__main__":
    run_experiment()
