#!/usr/bin/env python3
"""
Hurst Exponent Analysis.
Testing if local Hurst exponent predicts Z-Score Mean Reversion success.
Hypothesis: Fade |Z|>4 ONLY when Hurst < 0.5 (Mean Reverting Regime).
"""

import os
import sys
import numpy as np
import polars as pl
from hurst import compute_Hc
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data
from behemoth.core.events import simulate_trade
from behemoth.config import Z_STOP

# Constants
DATA_DIR = "data/global_1h"
HURST_WINDOW = 100 # Lookback for Hurst calculation
Z_ENTRY_REV = 4.0
Z_STOP_LEVEL = 8.0

PAIRS = [
    # Top Movers (Volatile)
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    # Known Reverters (from previous test)
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    # Known Failures (Trenders)
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
]

def rolling_hurst(series, window):
    """
    Compute rolling Hurst exponent.
    Very slow in Python loop. Using simplified R/S or optimized library?
    The `hurst` library compute_Hc is O(N log N).
    For rolling window, we might need a faster approximation or just accept slowness for research.
    """
    H_series = np.full(len(series), 0.5)
    
    # Pre-compute for speed? No, it's iterative.
    # Let's do a stride to save time? Every 10 bars?
    stride = 1
    
    print(f"  Computing Rolling Hurst (window={window})...")
    for i in range(window, len(series), stride):
        chunk = series[i-window:i]
        try:
            # simplified=True is faster
            H, c, data = compute_Hc(chunk, kind='price', simplified=True)
            H_series[i:i+stride] = H
        except:
            H_series[i:i+stride] = 0.5
            
    return H_series

def run_experiment():
    print("--- HURST EXPONENT FILTER EXPERIMENT ---")
    
    results = []
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Z-Scores (Signal)
        betas, errors, _ = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        # 2. Compute Rolling Hurst of the SPREAD (Residuals)
        # We want to know if the *spread* is mean reverting.
        hurst = rolling_hurst(errors, HURST_WINDOW)
        
        # 3. Simulate Trades (With and Without Filter)
        trades_all = 0
        pnl_all = 0
        
        trades_filter = 0
        pnl_filter = 0
        
        last_entry = 0
        min_gap = 20
        
        for i in range(500, len(y)-500):
            z = z_scores[i]
            H = hurst[i]
            
            # Entry Signal
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            # Direction
            if z > 0: dir = -1
            else: dir = 1
            
            # Outcome (Shared)
            # We assume active_leg logic is handled inside simulate_trade if we pass 'Y' as default/simple
            # For this test, let's just use 'Y' as active leg for simplicity or use select_active_leg
            # We need accurate PnL so let's do it right.
            # But wait, active_leg depends on Beta.
            active_asset = "Y" # Simplified for Hurst test
            
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            
            # 1. Unfiltered Strategy
            trades_all += 1
            pnl_all += pnl
            
            # 2. Hurst Filtered Strategy (H < 0.5)
            if H < 0.5:
                # Strong Mean Reversion Regime
                trades_filter += 1
                pnl_filter += pnl
                
            last_entry = i
            
        avg_all = pnl_all / trades_all if trades_all > 0 else 0
        avg_filter = pnl_filter / trades_filter if trades_filter > 0 else 0
        
        print(f"  ALL: {trades_all} trades, {pnl_all:.0f} bps ({avg_all:.1f} avg)")
        print(f"  H<0.5: {trades_filter} trades, {pnl_filter:.0f} bps ({avg_filter:.1f} avg)")
        print(f"  Improvement: {avg_filter - avg_all:.1f} bps per trade")
        
if __name__ == "__main__":
    run_experiment()
