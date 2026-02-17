#!/usr/bin/env python3
"""
FX Momentum Acceleration Experiment (WFO Params).
Using config.py params: Window=750, Z_Entry=1.5.
Universe: Pure FX (11 pairs).
Goal: Test if Acceleration improves FX Momentum performance.
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
# Import actual config values to be sure
from behemoth.config import Z_ENTRY_MOM, Z_STOP, Z_LOOKBACK, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH
from behemoth.core.active_leg import select_active_leg

# Override if needed, but let's stick to config

# Override if needed, but let's stick to config
MOM_WINDOW = Z_LOOKBACK # 750
Z_ENTRY = Z_ENTRY_MOM # 1.5
Z_STOP_LEVEL = 100.0 # Standard Momentum exits at 0 (Mean Reversion), so we set Stop (TP) high.

DATA_DIR = "data/global_1h"
THRESHOLDS = [0.01, 0.05, 0.1, 0.2]

# Pure FX Universe
PAIRS = [
    ("EUR/GBP", "EURUSD_1h.parquet", "GBPUSD_1h.parquet", "close", "close"),
    ("AUD/NZD", "NZDUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("EUR/CHF", "EURUSD_1h.parquet", "USDCHF_1h.parquet", "close", "close"),
    ("EUR/JPY", "EURUSD_1h.parquet", "USDJPY_1h.parquet", "close", "close"),
    ("GBP/JPY", "GBPUSD_1h.parquet", "USDJPY_1h.parquet", "close", "close"),
    ("CHF/JPY", "USDCHF_1h.parquet", "USDJPY_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("GBP/AUD", "GBPUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("AUD/CAD", "AUDUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close"),
    ("GBP/CAD", "GBPUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close"),
    ("NZD/CAD", "NZDUSD_1h.parquet", "USDCAD_1h.parquet", "close", "close"),
]

def run_experiment():
    print(f"--- FX MOMENTUM ACCEL (WFO: Win={MOM_WINDOW}, Z={Z_ENTRY}) ---")
    
    overall_base_pnl = 0
    overall_base_trades = 0
    
    # Store aggregate results per threshold
    thresh_results = {t: {"pnl": 0, "trades": 0} for t in THRESHOLDS}
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Kalman
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
        min_gap = 20
        
        for i in range(MOM_WINDOW, len(y)-200):
            z = z_scores[i]
            beta = betas[i]
            
            if abs(z) < Z_ENTRY: continue
            if i - last_entry < min_gap: continue
            
            # Select Active Leg
            active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_asset is None: continue # Skip neutral beta
            
            if z > 0: dir = 1
            else: dir = -1
            
            pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, active_asset, Z_ENTRY, Z_STOP_LEVEL)
            base_trades += 1
            base_pnl += pnl
            last_entry = i
            
        avg = base_pnl / base_trades if base_trades > 0 else 0
        print(f"  BASELINE: {base_trades} trades, {base_pnl:.0f} bps ({avg:.1f} avg)")
        overall_base_trades += base_trades
        overall_base_pnl += base_pnl
        
        # Filtered
        for thresh in THRESHOLDS:
            f_trades = 0
            f_pnl = 0
            last_entry = 0
            
            for i in range(MOM_WINDOW, len(y)-200):
                z = z_scores[i]
                acc = z_accel[i]
                beta = betas[i]
                
                if abs(z) < Z_ENTRY: continue
                if i - last_entry < min_gap: continue
                if acc <= thresh: continue 
                
                # Active Leg Check (Must match baseline)
                active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
                if active_asset is None: continue
                
                if z > 0: dir = 1
                else: dir = -1
                
                pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, active_asset, Z_ENTRY, Z_STOP_LEVEL)
                f_trades += 1
                f_pnl += pnl
                last_entry = i
                
            thresh_results[thresh]["trades"] += f_trades
            thresh_results[thresh]["pnl"] += f_pnl
            
            f_avg = f_pnl / f_trades if f_trades > 0 else 0

    # Report Aggregate
    print("\n--- AGGREGATE FX RESULTS ---")
    base_avg = overall_base_pnl / overall_base_trades if overall_base_trades > 0 else 0
    print(f"BASELINE (No Filter): {overall_base_trades} trades, {overall_base_pnl:.0f} bps ({base_avg:.1f} avg)")
    
    for t in THRESHOLDS:
        tr = thresh_results[t]["trades"]
        p = thresh_results[t]["pnl"]
        avg = p / tr if tr > 0 else 0
        imp = avg - base_avg
        print(f"Accel > {t:<4}: {tr:<5} trades, {p:<8.0f} bps ({avg:<6.1f} avg) | Imp: {imp:+.1f}")

if __name__ == "__main__":
    run_experiment()
