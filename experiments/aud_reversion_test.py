#!/usr/bin/env python3
"""
AUD Pairs Reversion Test.
User asks: "Why are AUD/NZD and EUR/AUD reverting? Can we trade them?"
Testing Reversion Strategies:
1. Fast Z (Window=100) Baseline
2. Fast Z + Deceleration (Accel < 1.0)
3. Fast Z + RSI Filter (RSI > 75 / < 25)
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
Z_STOP_LEVEL = 8.0 # Wide stop for simulation
ACCEL_THRESH = 1.0 
RSI_THRESH_HIGH = 75
RSI_THRESH_LOW = 25
RSI_PERIOD = 14

PAIRS = [
    ("AUD/NZD", "NZDUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
]

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50).to_numpy()

def run_experiment():
    print(f"--- AUD REVERSION TEST (Win={FAST_WINDOW}, Z={Z_ENTRY_REV}) ---")
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Kalman & Z
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        # 2. Compute Accel
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()
        
        # 3. Compute RSI (on Spread/Error)
        # Reversion usually filters based on RSI divergence or extreme.
        # Let's compute RSI of the *Spread Error*.
        rsi = compute_rsi(pd.Series(errors), period=RSI_PERIOD)
        
        # 4. Simulations
        # Baseline
        base_trades = 0
        base_pnl = 0
        last_entry = 0
        min_gap = 10
        
        # Decel Filter
        decel_trades = 0
        decel_pnl = 0
        last_entry_d = 0
        
        # RSI Filter
        rsi_trades = 0
        rsi_pnl = 0
        last_entry_r = 0
        
        for i in range(FAST_WINDOW + 50, len(y)-200):
            z = z_scores[i]
            
            # --- BASELINE ---
            if abs(z) > Z_ENTRY_REV and (i - last_entry > min_gap):
                if z > 0: dir = -1
                else: dir = 1
                pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, "Y", Z_ENTRY_REV, Z_STOP_LEVEL)
                base_trades += 1
                base_pnl += pnl
                last_entry = i
                
            # --- DECEL FILTER ---
            acc = z_accel[i]
            if abs(z) > Z_ENTRY_REV and (i - last_entry_d > min_gap) and (acc < ACCEL_THRESH):
                if z > 0: dir = -1
                else: dir = 1
                pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, "Y", Z_ENTRY_REV, Z_STOP_LEVEL)
                decel_trades += 1
                decel_pnl += pnl
                last_entry_d = i

            # --- RSI FILTER ---
            r = rsi[i]
            # Valid Reversion Setup:
            # If Z > 3 (Long Spread Overbought) -> We Short -> Need RSI > 75 (Overbought confirmation)
            # If Z < -3 (Short Spread Oversold) -> We Long -> Need RSI < 25 (Oversold confirmation)
            
            valid_rsi = False
            if z > 0 and r > RSI_THRESH_HIGH: valid_rsi = True
            if z < 0 and r < RSI_THRESH_LOW: valid_rsi = True
            
            if abs(z) > Z_ENTRY_REV and (i - last_entry_r > min_gap) and valid_rsi:
                 if z > 0: dir = -1
                 else: dir = 1
                 pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, "Y", Z_ENTRY_REV, Z_STOP_LEVEL)
                 rsi_trades += 1
                 rsi_pnl += pnl
                 last_entry_r = i

        # Results
        b_avg = base_pnl / base_trades if base_trades > 0 else 0
        d_avg = decel_pnl / decel_trades if decel_trades > 0 else 0
        r_avg = rsi_pnl / rsi_trades if rsi_trades > 0 else 0
        
        print(f"  BASELINE : {base_trades} trades, {base_pnl:.0f} bps ({b_avg:.1f} avg)")
        print(f"  DECEL (<1): {decel_trades} trades, {decel_pnl:.0f} bps ({d_avg:.1f} avg)")
        print(f"  RSI (>75): {rsi_trades} trades, {rsi_pnl:.0f} bps ({r_avg:.1f} avg)")

if __name__ == "__main__":
    run_experiment()
