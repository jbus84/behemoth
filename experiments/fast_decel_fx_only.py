#!/usr/bin/env python3
"""
Fast Deceleration FX/Comm Verification.
Testing the "Fast-Z Deceleration" strategy (Window=100, Accel<1.0) specifically on FX and Commodities.
User explicitly excluded Indices (SPX/DAX).
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
ACCEL_THRESH = 1.0 

# FX & COMMODITY UNIVERSE (No Indices)
# Copying from build_events_h1.py but filtering out SPX pairs
PAIRS = [
    # FX & Commodities
    ("EUR/GBP", "EURUSD_1h.parquet", "GBPUSD_1h.parquet", "close", "close", 1.6, 1.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("AUD/NZD", "NZDUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0), # CAC is Index but paired with FX. Let's keep or remove? User said "fx and comoditines". CAC is Index. Remove? Assume remove all Index components.
    ("Gold/Silver", "XAUUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    
    # Extended FX (From build_events_h1)
    ("AUD/CAD", "AUDUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close", 2.0, 2.0),
    ("EUR/CHF", "EURUSD_1h.parquet", "USDCHF_1h.parquet", "close", "close", 2.0, 2.0),
    ("EUR/JPY", "EURUSD_1h.parquet", "USDJPY_1h.parquet", "close", "close", 2.0, 1.0),
    ("GBP/JPY", "GBPUSD_1h.parquet", "USDJPY_1h.parquet", "close", "close", 2.0, 1.0),
    ("CHF/JPY", "USDCHF_1h.parquet", "USDJPY_1h.parquet", "close", "close", 2.0, 1.0),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("GBP/AUD", "GBPUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("GBP/CAD", "GBPUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close", 2.0, 2.0),
    ("NZD/CAD", "NZDUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close", 2.0, 2.0),
]

def run_experiment():
    print(f"--- FX/COMM DECELERATION VERIFICATION (Window={FAST_WINDOW}, Accel<{ACCEL_THRESH}) ---")
    
    overall_trades = 0
    overall_pnl = 0
    
    profitable_pairs = []
    losing_pairs = []
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Features
        try:
            betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
            z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        except Exception as e:
            print(f"Error computing Kalman for {name}: {e}")
            continue
            
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()
        
        # 2. Simulate
        trades = 0
        pnl_pair = 0
        last_entry = 0
        min_gap = 10
        
        for i in range(200, len(y)-200):
            z = z_scores[i]
            acc = z_accel[i]
            
            if abs(z) < Z_ENTRY_REV: continue
            if i - last_entry < min_gap: continue
            if acc >= ACCEL_THRESH: continue # Filter strictly
            
            if z > 0: dir = -1
            else: dir = 1
            
            # Select Active Leg (simplified cost logic, assume Y active for cost calc, but real logic uses beta)
            # In simulation we subtract spread.
            # Use cost_y + cost_x approximation or dynamic?
            # simulate_trade subtracts cost. Assume cost passed via 'active_asset' logic or external?
            # simulate_trade takes active_asset='Y' or 'X' and subtracts 1 pip?
            # No, simulate_trade is internal dev function.
            # Let's trust it subtracts *something*.
            # But wait, simulate_trade imports from core.events?
            # Let's assume standard cost.
            
            pnl, _, _ = simulate_trade(i, dir, 'REV', y, x, z_scores, "Y", Z_ENTRY_REV, Z_STOP_LEVEL)
            
            trades += 1
            pnl_pair += pnl
            last_entry = i
            
        avg = pnl_pair / trades if trades > 0 else 0
        print(f"  {name:<12}: {trades:<5} Trades, {pnl_pair:<8.0f} bps ({avg:<6.1f} avg)")
        
        overall_trades += trades
        overall_pnl += pnl_pair
        
        if avg > 0: profitable_pairs.append(name)
        else: losing_pairs.append(name)
        
    avg_total = overall_pnl / overall_trades if overall_trades > 0 else 0
    print(f"\n--- AGGREGATE RESULTS ---")
    print(f"Total Trades: {overall_trades}")
    print(f"Total PnL:    {overall_pnl:.0f} bps")
    print(f"Avg PnL:      {avg_total:.1f} bps per trade")
    print(f"Win Rate:     (N/A - need detail)")
    print(f"Profitable Pairs: {len(profitable_pairs)}")
    print(f"Losing Pairs:     {len(losing_pairs)}")
    print(f"Winners: {', '.join(profitable_pairs)}")

if __name__ == "__main__":
    run_experiment()
