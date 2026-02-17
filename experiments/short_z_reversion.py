#!/usr/bin/env python3
"""
Short-Z Reversion Experiment.
Hypothesis: Reversion happens on shorter timescales than Momentum.
Test: Use Lookback=100 (instead of 750) for Z-Score calculation.
Strategy: Scalp Reversions (Fade |Z_100| > 4.0).
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
THRESHOLDS = [2.5, 3.0, 4.0]
Z_STOP_LEVEL = 8.0

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0),
]

def run_experiment():
    print(f"--- SHORT-Z REVERSION EXPERIMENT (Window={FAST_WINDOW}) ---")
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute FAST Z-Scores (Window=100)
        # Note: compute_kalman_states has default window=750 inside?
        # We need to pass window argument or modify it?
        # Checking implementation: compute_kalman_states(y, x, window=750)
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        # 2. Simulate Reversion Trade per Threshold
        for thresh in THRESHOLDS:
            trades = 0
            pnl_total = 0
            last_entry = 0
            min_gap = 10 
            
            for i in range(200, len(y)-200): # Start earlier
                z = z_scores[i]
                
                # Entry Signal
                if abs(z) < thresh: continue
                if i - last_entry < min_gap: continue
                
                # Direction: Fade
                if z > 0: dir = -1 # Short
                else: dir = 1 # Long
                
                active_asset = "Y"
                
                pnl, duration, outcomes = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, thresh, Z_STOP_LEVEL)
                
                trades += 1
                pnl_total += pnl
                last_entry = i
            
            avg_pnl = pnl_total / trades if trades > 0 else 0
            print(f"  [Z>={thresh}] Trades: {trades}, Total PnL: {pnl_total:.0f} bps, Avg: {avg_pnl:.1f} bps")
        
        # Calculate Win Rate?
        # simulate_trade returns pnl. Positive is Win.
        
if __name__ == "__main__":
    run_experiment()
