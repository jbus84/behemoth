#!/usr/bin/env python3
"""
Hybrid Reversion Experiment.
Testing if Technical Indicators (RSI) predict Z-Score Reversion success.
Hypothesis: Fade |Z|>4 ONLY when RSI is extreme (>75 or <25).
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
Z_ENTRY_REV = 4.0
Z_STOP_LEVEL = 8.0
RSI_WINDOW = 14
RSI_THRESH_HIGH = 75
RSI_THRESH_LOW = 25

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0),
]

def compute_rsi(series, window=14):
    """
    Compute Rolling RSI.
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50).to_numpy()

def run_experiment():
    print("--- RSI HYBRID FILTER EXPERIMENT ---")
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Z-Scores (Signal)
        betas, errors, _ = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        # 2. Compute RSI on the SPREAD (Residuals)
        # Reversion usually means Spread is overbought/oversold.
        # So we check RSI of the error term.
        rsi = compute_rsi(pd.Series(errors), window=RSI_WINDOW)
        
        # 3. Simulate Trades (With and Without Filter)
        trades_all = 0
        pnl_all = 0
        
        trades_filter = 0
        pnl_filter = 0
        
        last_entry = 0
        min_gap = 20
        
        for i in range(500, len(y)-500):
            z = z_scores[i]
            r = rsi[i]
            
            # Entry Signal
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            
            # Direction
            if z > 0: dir = -1 # Short
            else: dir = 1 # Long
            
            # Outcome
            active_asset = "Y"
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, active_asset, Z_ENTRY_REV, Z_STOP_LEVEL)
            
            trades_all += 1
            pnl_all += pnl
            
            # Filter Logic:
            # If Shorting (Z high), need RSI High (Overbought) > 75
            # If Longing (Z low), need RSI Low (Oversold) < 25
            valid = False
            if dir == -1 and r > RSI_THRESH_HIGH: valid = True
            elif dir == 1 and r < RSI_THRESH_LOW: valid = True
            
            if valid:
                trades_filter += 1
                pnl_filter += pnl
                
            last_entry = i
            
        avg_all = pnl_all / trades_all if trades_all > 0 else 0
        avg_filter = pnl_filter / trades_filter if trades_filter > 0 else 0
        
        print(f"  ALL: {trades_all} trades, {pnl_all:.0f} bps ({avg_all:.1f} avg)")
        print(f"  RSI Filter: {trades_filter} trades, {pnl_filter:.0f} bps ({avg_filter:.1f} avg)")
        print(f"  Improvement: {avg_filter - avg_all:.1f} bps per trade")
        
if __name__ == "__main__":
    run_experiment()
