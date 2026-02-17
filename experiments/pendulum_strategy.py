#!/usr/bin/env python3
"""
Pendulum Strategy Experiment.
Hypothesis: Mean Reversion has momentum. If Z crosses 0 from an extreme, it continues to the other extreme.
Logic:
1. Monitor Z-Score (Window=100).
2. Track Peak Z since last Zero Cross.
3. If Z crosses 0 AND |Peak Z| > THRESH_PEAK:
   - Enter Trade (Follow the cross).
   - Target: |Z| = TARGET_Z (Other side).
   - Stop: |Z| = STOP_Z (False breakout).
"""

import os
import sys
import numpy as np
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores
from behemoth.io.loaders import load_pair_data
# We need custom simulation logic for this state machine
# simulate_trade in core/events is based on simple threshold entry/exit.
# We'll implement a simple one here.

# Constants
DATA_DIR = "data/global_1h"
FAST_WINDOW = 100
THRESH_PEAK = 2.0 # Must have come from at least 2.0 sigma
TARGET_Z = 2.0    # Target the other side's 2.0 sigma
STOP_Z = 0.5      # Stop if it whipsaws back into previous zone by 0.5

PAIRS = [
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("EUR/AUD", "EURUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0),
]

def run_experiment():
    print(f"--- PENDULUM STRATEGY (Window={FAST_WINDOW}) ---")
    print(f"Logic: If cross 0 from > {THRESH_PEAK}, Target -{TARGET_Z}, Stop +/- {STOP_Z}")
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        print(f"\nProcessing {name}...")
        df = load_pair_data(DATA_DIR, fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        betas, errors, _ = compute_kalman_states(y, x, window=FAST_WINDOW)
        z_scores = compute_z_scores(errors, window=FAST_WINDOW)
        
        # State Machine
        peak_z = 0
        current_zone = 0 # 1 (Pos), -1 (Neg)
        
        trades = 0
        pnl_total = 0
        
        in_trade = False
        trade_dir = 0
        entry_idx = 0
        entry_price_y = 0
        entry_price_x = 0
        entry_beta = 0
        
        # Init state
        if z_scores[100] > 0: current_zone = 1
        else: current_zone = -1
        
        for i in range(101, len(y)):
            z = z_scores[i]
            
            # Update Peak for current zone
            if current_zone == 1:
                peak_z = max(peak_z, z)
            else:
                peak_z = min(peak_z, z)
                
            # Check Zero Cross
            cross = False
            if current_zone == 1 and z < 0:
                # Crossed Positive -> Negative
                cross = True
                new_zone = -1
            elif current_zone == -1 and z > 0:
                # Crossed Negative -> Positive
                cross = True
                new_zone = 1
                
            if cross:
                # 1. Manage Existing Trade (if any)
                # If we cross 0, technically the "Pendulum" trade would have started at the PREVIOUS cross?
                # No, the logic says: "Recently cross 1.5 and then 0, keep going to next 1.5".
                # So we ENTER at 0.
                
                # If we were already in a trade targeting this side, great. But usually we enter ON the cross.
                # If we are in a trade, a zero cross "against" us is a stop (failed to reach target).
                # But here the cross IS the signal.
                
                # Check Entry Signal
                valid_setup = False
                if current_zone == 1: # Came from Positive
                    if peak_z > THRESH_PEAK: valid_setup = True
                    trade_signal_dir = -1 # Short (Downwards momentum)
                else: # Came from Negative
                    if peak_z < -THRESH_PEAK: valid_setup = True
                    trade_signal_dir = 1 # Long (Upwards momentum)
                    
                if valid_setup and not in_trade:
                    # ENTER TRADE
                    in_trade = True
                    trade_dir = trade_signal_dir
                    entry_idx = i
                    entry_price_y = y[i]
                    entry_price_x = x[i]
                    entry_beta = betas[i]
                    # Reset Peak for new zone is not needed, handled by zone switch
                
                # Switch Zone
                current_zone = new_zone
                peak_z = z # Reset peak to current z (start of new zone)
                
            # Manage Active Trade
            if in_trade:
                active_cost = cost_y # Simplified
                
                # Target Hit?
                target_hit = False
                if trade_dir == 1 and z > TARGET_Z: target_hit = True
                if trade_dir == -1 and z < -TARGET_Z: target_hit = True
                
                # Stop Hit? (Recoil back to 0.5 of PREVIOUS zone)
                # If Long (Target +2), Stop is < -0.5 (Wait, we are in + zone now).
                # No, we just crossed 0. So Z should be increasing.
                # If Z goes back to -0.5 (into the zone we just left), it's a fakeout.
                stop_hit = False
                if trade_dir == 1 and z < -STOP_Z: stop_hit = True
                if trade_dir == -1 and z > STOP_Z: stop_hit = True
                
                exit = False
                outcome = ""
                
                if target_hit:
                    exit = True
                    outcome = "WIN"
                elif stop_hit:
                    exit = True
                    outcome = "LOSS"
                    
                if exit:
                    # Calc PnL
                    ret_y = y[i] - entry_price_y
                    ret_x = x[i] - entry_price_x
                    pnl = trade_dir * (ret_y - entry_beta * ret_x) * 10000
                    pnl -= active_cost * 2 # Spread cost approx
                    
                    pnl_total += pnl
                    trades += 1
                    in_trade = False
                    
        avg = pnl_total / trades if trades > 0 else 0
        print(f"  Trades: {trades}, Total PnL: {pnl_total:.0f} bps, Avg: {avg:.1f} bps")

if __name__ == "__main__":
    run_experiment()
