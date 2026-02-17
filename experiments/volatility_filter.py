#!/usr/bin/env python3
"""
Volatility Filter Experiment.
Testing if Low Volatility Regime predicts Reversion success.
Hypothesis: Fade |Z|>4 ONLY when recent volatility is LOW (Range Bound).
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
VOL_WINDOW = 24 # 1 Day lookback for volatility context
Z_ENTRY_REV = 4.0
Z_STOP_LEVEL = 8.0

PAIRS = [
    # Top Movers (Volatile)
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    # Known Reverters
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    # Known Failures
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0),
]

def compute_vol_filter(y, x, window=24):
    """
    Compute relative volatility percentile.
    Using spread/residual volatility?
    The signal is driven by Z-score (residuals).
    If residual volatility is expanding, it's a trend.
    If residual volatility is contracting, maybe range?
    Let's use rolling std of residuals.
    """
    # Just return the rolling std series
    return pd.Series(y-x).rolling(window=window).std().to_numpy() # Raw estimate

def run_experiment():
    print("--- VOLATILITY FILTER EXPERIMENT ---")
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Z-Scores (Signal)
        # Use Kalman residuals for Z-score foundation
        betas, errors, _ = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        # 2. Compute Volatility Context
        # Rolling Std Dev of the errors (residuals) over last 24 hours
        # Normalize by longer term (100 hours) to see if it's "Low Vol" relative to recent history?
        # Ratio = ShortVol / LongVol.
        # If Ratio < 1.0 -> Contracting Vol -> Range?
        # If Ratio > 1.0 -> Expanding Vol -> Trend?
        
        errors_s = pd.Series(errors)
        short_vol = errors_s.rolling(24).std()
        long_vol = errors_s.rolling(120).std() # 5 days
        
        vol_ratio = (short_vol / long_vol).to_numpy()
        
        # Fill NaNs
        vol_ratio = np.nan_to_num(vol_ratio, nan=1.0)
        
        # 3. Simulate Trades (With and Without Filter)
        trades_all = 0
        pnl_all = 0
        
        trades_filter = 0
        pnl_filter = 0
        
        last_entry = 0
        min_gap = 20
        
        # Threshold: Only trade if Vol Ratio < 0.8 (Quiet Market)
        FILTER_THRESH = 0.8
        
        for i in range(500, len(y)-500):
            z = z_scores[i]
            vr = vol_ratio[i]
            
            # Entry Signal
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            # Direction
            if z > 0: dir = -1
            else: dir = 1
            
            active_asset = "Y" # Simplified
            
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            
            # 1. Unfiltered Strategy
            trades_all += 1
            pnl_all += pnl
            
            # 2. Volatility Filtered Strategy (Quiet Market)
            if vr < FILTER_THRESH:
                trades_filter += 1
                pnl_filter += pnl
                
            last_entry = i
            
        avg_all = pnl_all / trades_all if trades_all > 0 else 0
        avg_filter = pnl_filter / trades_filter if trades_filter > 0 else 0
        
        print(f"  ALL: {trades_all} trades, {pnl_all:.0f} bps ({avg_all:.1f} avg)")
        print(f"  LowVol (<{FILTER_THRESH}): {trades_filter} trades, {pnl_filter:.0f} bps ({avg_filter:.1f} avg)")
        print(f"  Improvement: {avg_filter - avg_all:.1f} bps per trade")
        
if __name__ == "__main__":
    run_experiment()
