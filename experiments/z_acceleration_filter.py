#!/usr/bin/env python3
"""
Z-Acceleration Filter Experiment.
Hypothesis: Reversion occurs when momentum slows down (Deceleration).
Filter: Fade |Z| > 3.0 ONLY if Z-Acceleration (Change in Velocity) < THRESH.
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
FAST_WINDOW = 100
Z_ENTRY_REV = 3.0
Z_STOP_LEVEL = 8.0
ACCEL_THRESH = 1.0 # Strict deceleration required

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close"),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close"),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close"),
]

def run_experiment():
    print(f"--- Z-ACCELERATION FILTER (Window={FAST_WINDOW}, Thresh={ACCEL_THRESH}) ---")
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()
        
        trades_all = 0
        pnl_all = 0
        trades_filter = 0
        pnl_filter = 0
        last_entry = 0
        min_gap = 10
        
        for i in range(200, len(y)-200):
            z = z_scores[i]
            acc = z_accel[i]
            
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            # Direction
            if z > 0: dir = -1
            else: dir = 1
            
            active_asset = "Y"
            
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            
            trades_all += 1
            pnl_all += pnl
            
            if acc < ACCEL_THRESH:
                trades_filter += 1
                pnl_filter += pnl
                
            last_entry = i
            
        avg_all = pnl_all / trades_all if trades_all > 0 else 0
        avg_filter = pnl_filter / trades_filter if trades_filter > 0 else 0
        
        print(f"  ALL: {trades_all} trades, {pnl_all:.0f} bps ({avg_all:.1f} avg)")
        print(f"  LowAccel (<{ACCEL_THRESH}): {trades_filter} trades, {pnl_filter:.0f} bps ({avg_filter:.1f} avg)")
        print(f"  Improvement: {avg_filter - avg_all:.1f} bps per trade")

if __name__ == "__main__":
    run_experiment()
