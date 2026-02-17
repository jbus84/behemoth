#!/usr/bin/env python3
"""
Mean Reversion Prospecting (H1).
Target: Z > 4.0 (Extreme deviation).
Strategy: Fade the move (Short if Z>4, Long if Z<-4). Exit at Z=0.
"""

import os
import sys
from collections import defaultdict
import numpy as np
import polars as pl
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Constants (Overridden for Experiment)
Z_ENTRY_REV = 4.0
Z_STOP = 8.0  # Wide stop for extreme reversion
MIN_GAP_BARS = 20
ACTIVE_LEG_LOW = 0.98
ACTIVE_LEG_HIGH = 1.02

from behemoth.core.active_leg import select_active_leg
from behemoth.core.events import simulate_trade as _simulate_trade
from behemoth.core.kalman import compute_kalman_states as _compute_kalman_states
from behemoth.core.zscore import compute_z_scores as _compute_z_scores
from behemoth.io.loaders import load_pair_data as _load_pair_data

DATA_DIR = "data/global_1h"
OUTPUT_DIR = "data/events"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === PAIR UNIVERSE (Same as H1 Pipeline) ===
PAIRS = [
    # FX & Commodities
    ("EUR/GBP", "EURUSD_1h.parquet", "GBPUSD_1h.parquet", "close", "close", 1.6, 1.0),
    ("Gold/Oil", "BCOUSD_1h.parquet", "XAUUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("Oil/Silver", "BCOUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    ("AUD/NZD", "NZDUSD_1h.parquet", "AUDUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("CAC/NZD", "NZDUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 3.0),
    ("Gold/Silver", "XAUUSD_1h.parquet", "XAGUSD_1h.parquet", "close", "close", 3.0, 3.0),
    # Global Equities
    ("SPX/DAX", "SPXUSD_1h.parquet", "GRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("SPX/CAC", "SPXUSD_1h.parquet", "FRXEUR_1h.parquet", "close", "close", 3.0, 2.0),
    ("SPX/FTSE", "SPXUSD_1h.parquet", "UKXGBP_1h.parquet", "close", "close", 3.0, 2.0),
    ("SPX/Nikkei", "SPXUSD_1h.parquet", "JPXJPY_1h.parquet", "close", "close", 3.0, 2.0),
    ("SPX/HK", "SPXUSD_1h.parquet", "HKXHKD_1h.parquet", "close", "close", 4.0, 2.0),
    ("SPX/Dow", "SPXUSD_1h.parquet", "UDXUSD_1h.parquet", "close", "close", 2.0, 2.0),
    ("SPX/Nas", "SPXUSD_1h.parquet", "NSXUSD_1h.parquet", "close", "close", 2.0, 2.0),
    # Extended FX
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

def load_pair_data(fx, fy, cx, cy):
    return _load_pair_data(DATA_DIR, fx, fy, cx, cy)

def compute_kalman_states(y, x):
    return _compute_kalman_states(y, x)

def compute_z_scores(errors, window=750):
    return _compute_z_scores(errors, window=window)

def simulate_trade(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh=1.5, stop=3.5):
    return _simulate_trade(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh, stop)


def run_experiment():
    print("--- MEAN REVERSION PROSPECTING (Z > 4.0) ---")
    
    thresh_rev = Z_ENTRY_REV # 4.0
    stop_level = Z_STOP      # 8.0
    
    print(f"Configuration: Entry |Z| >= {thresh_rev}, Exit Z=0, Stop |Z| >= {stop_level}")

    all_events = []
    
    # Phase 1: Load and Process
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None: continue
            
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        betas, errors, ret_betas = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        # Phase 2: Sim Trades
        last_entry_rev = 0
        min_gap = MIN_GAP_BARS
        
        # Track stats for this pair
        pair_trades = 0
        pair_pnl = 0
        
        for i in range(500, len(y) - 500):
            z = z_scores[i]
            beta = betas[i]
            
            # Active Asset Check
            active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_asset == "Y": cost = cost_y
            elif active_asset == "X": cost = cost_x
            else: continue
            
            # Entry Check
            if abs(z) < thresh_rev: continue
            
            # Check Gap
            if i - last_entry_rev < min_gap: continue
            
            # Direction: FADE (Reversion)
            if z > 0:
                rev_dir = -1 # Short (Z is positive/high, bet it goes down)
            else:
                rev_dir = 1 # Long (Z is negative/low, bet it goes up)
                
            # Simulate
            pnl, duration, outcome = simulate_trade(
                i, rev_dir, 'REV', y, x, z_scores, active_asset, thresh_rev, stop_level
            )
            
            # Save
            row = {
                "pair": name,
                "timestamp": ts[i],
                "year": int(str(ts[i])[:4]),
                "strategy_type": "REV",
                "active_leg": active_asset,
                "side": "LONG" if rev_dir == 1 else "SHORT",
                "outcome": outcome,
                "pnl_bps": round(pnl, 2),
                "duration_bars": duration
            }
            all_events.append(row)
            last_entry_rev = i
            
            pair_trades += 1
            pair_pnl += pnl
            
        if pair_trades > 0:
            avg = pair_pnl / pair_trades
            print(f"{name:<15}: {pair_trades:<5} Trades, PnL: {pair_pnl:<10.0f} bps, Avg: {avg:<6.2f} bps")
        else:
            print(f"{name:<15}: 0 Trades")

    # Phase 3: Save
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_h1_reversion_prospect.csv")
        df_out.write_csv(out_path)
        print(f"\nSaved {len(all_events)} reversion trades to {out_path}")
        
if __name__ == "__main__":
    run_experiment()
