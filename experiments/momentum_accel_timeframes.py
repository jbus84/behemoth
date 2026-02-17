#!/usr/bin/env python3
"""
M15/M5 Momentum Acceleration Experiment.
Testing the "Momentum Acceleration" strategy (Window=750, Z=1.5, Ride Trend) on M15 and M5 timeframes.
Hypothesis: Lower timeframes might offer more frequent "micro-trends" that acceleration can catch.
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
from behemoth.config import Z_ENTRY_MOM, Z_STOP, Z_LOOKBACK, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH
from behemoth.core.active_leg import select_active_leg

# Constants
MOM_WINDOW = 750 # Keeping constant as requested
Z_ENTRY = 1.5
Z_STOP_LEVEL = 100.0 # Ride Trend
THRESHOLDS = [0.01, 0.05, 0.1, 0.2]

# Pairs to test (Mix of Trend and Reversion candidates)
# Format: Name, FileY, FileX
PAIRS_DEF = [
    ("GBP/JPY", "GBPUSD", "USDJPY"),
    ("CHF/JPY", "USDCHF", "USDJPY"),
    ("EUR/JPY", "EURUSD", "USDJPY"),
    ("AUD/CAD", "AUDUSD", "USDCAD"),
    ("Gold/Oil", "BCOUSD", "XAUUSD"),
    ("EUR/GBP", "EURUSD", "GBPUSD"),
    ("EUR/AUD", "EURUSD", "AUDUSD"),
    ("AUD/NZD", "NZDUSD", "AUDUSD"),
]

def run_timeframe(tf_name, data_dir, suffix):
    print(f"\n{'='*40}")
    print(f"--- TESTING TIMEFRAME: {tf_name} ---")
    print(f"{'='*40}")
    
    total_trades = 0
    total_pnl = 0
    
    # Per-Threshold Aggregates
    thresh_agg = {t: {"pnl": 0, "trades": 0} for t in THRESHOLDS}
    
    for name, f_y_base, f_x_base in PAIRS_DEF:
        fx = f"{f_x_base}_{suffix}.parquet"
        fy = f"{f_y_base}_{suffix}.parquet"
        
        # M15/M5 files use 'close_{SYM}' format
        cx = f"close_{f_x_base}"
        cy = f"close_{f_y_base}"
        
        df = load_pair_data(data_dir, fx, fy, cx, cy)
        if df is None: 
            print(f"Skipping {name} (Missing Data or Cols {cx}/{cy})")
            continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Kalman
        betas, errors, _ = compute_kalman_states(y, x, window=MOM_WINDOW)
        z_scores = compute_z_scores(errors, window=MOM_WINDOW)
        
        # 2. Accel
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()
        
        # Baseline
        base_trades = 0
        base_pnl = 0
        last_entry = 0
        min_gap = 20 # Bars
        
        for i in range(MOM_WINDOW, len(y)-200):
            z = z_scores[i]
            beta = betas[i]
            
            if abs(z) < Z_ENTRY: continue
            if i - last_entry < min_gap: continue
            
            active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_asset is None: continue
            
            if z > 0: dir = 1
            else: dir = -1
            
            pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, active_asset, Z_ENTRY, Z_STOP_LEVEL)
            base_trades += 1
            base_pnl += pnl
            last_entry = i
            
        avg = base_pnl / base_trades if base_trades > 0 else 0
        print(f"  {name:<10}: {base_trades:<5} trades, {base_pnl:<8.0f} bps ({avg:<6.1f} avg)")
        total_trades += base_trades
        total_pnl += base_pnl
        
        # Filtered
        for t in THRESHOLDS:
            f_trades = 0
            f_pnl = 0
            last_entry = 0
            for i in range(MOM_WINDOW, len(y)-200):
                z = z_scores[i]
                acc = z_accel[i]
                beta = betas[i]
                
                if abs(z) < Z_ENTRY: continue
                if i - last_entry < min_gap: continue
                if acc <= t: continue
                
                active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
                if active_asset is None: continue
                
                if z > 0: dir = 1
                else: dir = -1
                
                pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, active_asset, Z_ENTRY, Z_STOP_LEVEL)
                f_trades += 1
                f_pnl += pnl
                last_entry = i
            
            thresh_agg[t]["trades"] += f_trades
            thresh_agg[t]["pnl"] += f_pnl

    # Report for Timeframe
    print(f"\n--- {tf_name} AGGREGATE ---")
    base_avg = total_pnl / total_trades if total_trades > 0 else 0
    print(f"BASELINE: {total_trades} trades, {total_pnl:.0f} bps ({base_avg:.1f} avg)")
    
    for t in THRESHOLDS:
        tr = thresh_agg[t]["trades"]
        p = thresh_agg[t]["pnl"]
        avg = p / tr if tr > 0 else 0
        imp = avg - base_avg
        print(f"Accel > {t:<4}: {tr:<5} trades, {p:<8.0f} bps ({avg:<6.1f} avg) | Imp: {imp:+.1f}")

def run_experiment():
    # Run M15
    run_timeframe("M15", "data/global_15m", "15m")
    
    # Run M5
    run_timeframe("M5", "data/global_5m", "5m")

if __name__ == "__main__":
    run_experiment()
