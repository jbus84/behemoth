#!/usr/bin/env python3
"""
Z-Velocity Filter Experiment.
Hypothesis: Reversion works when price GRINDS to an extreme (Low Velocity).
Reversion fails when price EXPLODES to an extreme (High Velocity).
Filter: Fade |Z| > 3.0 ONLY if Z-Velocity (5-bar change) < THRESH.
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
Z_STOP_LEVEL = 8.0 # Wide stop
VELOCITY_THRESH = 5.0 # Max Z-Change over 5 bars allowed for entry

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close"),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close"),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close"),
]

def run_experiment():
    print(f"--- Z-VELOCITY FILTER (Window={FAST_WINDOW}, Thresh={VELOCITY_THRESH}) ---")
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Kalman States
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        # 2. Compute Z-Velocity
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(5).abs().fillna(0).to_numpy()
        
        # 3. Simulation Breakdown
        trades_all = 0
        pnl_all = 0
        
        trades_filter = 0
        pnl_filter = 0
        
        last_entry = 0
        min_gap = 10
        
        for i in range(200, len(y)-200):
            z = z_scores[i]
            vel = z_vel[i]
            
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            # Direction
            if z > 0: dir = -1
            else: dir = 1
            
            active_asset = "Y"
            
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            
            # All Trades
            trades_all += 1
            pnl_all += pnl
            
            # Filtered Trades (Low Velocity Only)
            if vel < VELOCITY_THRESH:
                trades_filter += 1
                pnl_filter += pnl
                
            last_entry = i
            
        avg_all = pnl_all / trades_all if trades_all > 0 else 0
        avg_filter = pnl_filter / trades_filter if trades_filter > 0 else 0
        
        print(f"  ALL: {trades_all} trades, {pnl_all:.0f} bps ({avg_all:.1f} avg)")
        print(f"  LowVel (<{VELOCITY_THRESH}): {trades_filter} trades, {pnl_filter:.0f} bps ({avg_filter:.1f} avg)")
        print(f"  Improvement: {avg_filter - avg_all:.1f} bps per trade")
        
        # Win Rate Comparison?
        # Sim function doesn't return outcome boolean easily (returns string/pnl).
        # Avg PnL is most important.

if __name__ == "__main__":
    run_experiment()
