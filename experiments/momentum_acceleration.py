#!/usr/bin/env python3
"""
Momentum Acceleration Filter Experiment.
Hypothesis: Trends begin with an ACCELERATION away from the mean.
A slow drift (low acceleration) above Z=2.0 is likely noise.
Filter: Enter Momentum Trade (|Z|>2.0) ONLY if Z-Acceleration > THRESH.
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
MOM_WINDOW = 750
Z_ENTRY_MOM = 2.0
Z_STOP_LEVEL = 0.0 # Momentum exits at 0 (Mean Reversion of trend) or Trailing stop logic?
# Standard Momentum Logic in simulate_trade:
# If type='MOM', exit when Z crosses 0? No, usually momentum holds until Z reverts?
# Let's check simulate_trade logic or reimplement simple version.
# Re-implementing ensure clarity.

THRESHOLDS = [0.01, 0.05, 0.1, 0.2]

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close"),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close"),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close"),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close"),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close"),
]

def run_experiment():
    print(f"--- MOMENTUM ACCELERATION FLITER (Window={MOM_WINDOW}) ---")
    
    for name, fx, fy, cx, cy in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        
        # 1. Compute Kalman States
        betas, errors, _ = compute_kalman_states(y, x, window=MOM_WINDOW)
        z_scores = compute_z_scores(errors, window=MOM_WINDOW)
        
        # 2. Compute Z-Acceleration
        z_series = pd.Series(z_scores)
        z_vel = z_series.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy() # 2nd derivative of Z
        
        # 3. Simulate Momentum
        # Logic: Enter Long Spread (Bet on divergence) if Z > 2.0 (Breakout UP)
        # Enter Short Spread if Z < -2.0 (Breakout DOWN)
        # Exit when Z crosses 0? Or fixed stop?
        # Standard Momentum: Enter at 2.0, Exit at 0.0 (or Profit Target?).
        # Usually Mom strategies ride the wave. If Z goes 2->4->6->4->2->0, we profit.
        # But if Z goes 2->1->0, we lose.
        # Let's use simulate_trade('MOM', ..., exit_z=0)
        
        # Baseline
        base_trades = 0
        base_pnl = 0
        last_entry = 0
        min_gap = 20
        
        for i in range(MOM_WINDOW, len(y)-200):
            z = z_scores[i]
            if abs(z) < Z_ENTRY_MOM: continue
            if i - last_entry < min_gap: continue
            
            # Momentum Direction: Follow the Z
            if z > 0: dir = 1 # Long Spread (Betting on higher Z? No. Betting on Divergence?)
            else: dir = -1 # Short Spread
            
            # Wait. "Momentum" in Pairs Trading usually means:
            # "The spread is widening, and will widen further."
            # So if Z > 2, we Long Spread.
            # But eventually perfectly cointegrated pairs revert.
            # So this is betting on "Breakdown of Cointegration".
            # Exit? Maybe trailing stop or fixed profit?
            # Let's assume standard 'MOM' logic in simulate_trade handles this.
            
            pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, "Y", Z_ENTRY_MOM, Z_STOP_LEVEL) # Z_STOP for MOM is usually 0 (reversion)
            
            base_trades += 1
            base_pnl += pnl
            last_entry = i
            
        avg = base_pnl / base_trades if base_trades > 0 else 0
        print(f"  BASELINE: {base_trades} trades, {base_pnl:.0f} bps ({avg:.1f} avg)")
        
        # Filtered Tests
        for thresh in THRESHOLDS:
            f_trades = 0
            f_pnl = 0
            last_entry = 0
            
            for i in range(MOM_WINDOW, len(y)-200):
                z = z_scores[i]
                acc = z_accel[i]
                
                if abs(z) < Z_ENTRY_MOM: continue
                if i - last_entry < min_gap: continue
                if acc <= thresh: continue # Filter: Must have Acceleration > Thresh
                
                if z > 0: dir = 1
                else: dir = -1
                
                pnl, _, _ = simulate_trade(i, dir, 'MOM', y, x, z_scores, "Y", Z_ENTRY_MOM, Z_STOP_LEVEL)
                f_trades += 1
                f_pnl += pnl
                last_entry = i
                
            f_avg = f_pnl / f_trades if f_trades > 0 else 0
            print(f"  [Accel>{thresh}] {f_trades} trades, {f_pnl:.0f} bps ({f_avg:.1f} avg)")

if __name__ == "__main__":
    run_experiment()
