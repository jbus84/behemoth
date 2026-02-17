#!/usr/bin/env python3
"""
Event dataset builder (H4).
Generates MOM/REV trades for analysis based on 4-Hour candles (Resampled from H1).
"""

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.config import (
    Z_ENTRY_MOM,
    Z_ENTRY_REV,
    Z_STOP,
    MIN_GAP_BARS,
    ACTIVE_LEG_LOW,
    ACTIVE_LEG_HIGH,
    MOM_ACCEL_THRESH,
    REV_ACCEL_THRESH,
)
from behemoth.core.active_leg import select_active_leg
from behemoth.core.events import simulate_trade as _simulate_trade
from behemoth.core.kalman import compute_kalman_states as _compute_kalman_states
from behemoth.core.zscore import compute_z_scores as _compute_z_scores
from behemoth.io.loaders import load_pair_data as _load_pair_data

DATA_DIR = "data/global_1h"
OUTPUT_DIR = "data/events"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === PAIR UNIVERSE ===
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


def build_dataset():  # pragma: no cover
    print("--- BUILDING EVENT DATASET (H4, MOM/REV) ---")

    thresh_mom = Z_ENTRY_MOM
    thresh_rev = Z_ENTRY_REV
    stop_level = Z_STOP
    min_gap = MIN_GAP_BARS

    # Phase 1: Load all data
    print("Phase 1: Loading data, resampling to H4, and computing Kalman states...")
    pair_states = {}

    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
            
        # Convert to pandas for resampling
        df = df.to_pandas()
            
        # === H4 RESAMPLING ===
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").resample("4h").agg({
            "Y": "last",
            "X": "last"
        }).dropna().reset_index()

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].astype(str).to_numpy() # Convert back to string for consistency

        betas, errors, ret_betas = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        # Compute Acceleration (2nd Derivative of Z)
        z_s = pl.Series(z_scores).to_pandas()
        z_vel = z_s.diff(1).abs()
        z_accel = z_vel.diff(1).abs().fillna(0).to_numpy()

        pair_states[name] = {
            'y': y, 'x': x, 'ts': ts,
            'betas': betas, 'errors': errors, 'ret_betas': ret_betas, 'z_scores': z_scores,
            'z_accel': z_accel,
            'cost_y': cost_y, 'cost_x': cost_x
        }
        print(f"  {name}: {len(y)} H4 bars")

    # Phase 2: Generate BOTH strategy types for each signal
    print("\nPhase 2: Generating dual-strategy events...")
    all_events = []
    
    # We use 0.0 threshold here to generate the "Unfiltered" baseline for analysis script to filter later
    # Force 0.0 accel for generation
    accel_thresh_override = 0.0 

    for name, state in pair_states.items():
        print(f"  Processing {name}...")

        y, x, ts = state['y'], state['x'], state['ts']
        betas, errors, ret_betas, z_scores = state['betas'], state['errors'], state['ret_betas'], state['z_scores']
        z_accel = state['z_accel']
        cost_y, cost_x = state['cost_y'], state['cost_x']

        last_entry_mom = 0
        last_entry_rev = 0
        
        # Use a smaller start buffer if H4 data is shorter? 
        # 500 bars H4 = 2000 hours = ~83 days. Reasonable.
        start_idx = 500
        
        for i in range(start_idx, len(y) - 1): # Just go to end
            z = z_scores[i]
            beta = betas[i]
            acc = z_accel[i]

            # Determine active asset based on Whip/Tank
            active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_asset == "Y":
                cost = cost_y
            elif active_asset == "X":
                cost = cost_x
            else:
                continue  # Skip neutral zone

            # === MOMENTUM TRADE ===
            if abs(z) > Z_ENTRY_MOM and (i - last_entry_mom > min_gap):
                if acc > accel_thresh_override: # Effectively always true if 0.0
                    if z > 0:
                        direction = 1 
                    else:
                        direction = -1 
                    
                    pnl, duration, outcome = _simulate_trade(
                        i, direction, "MOM", y, x, z_scores, active_asset, Z_ENTRY_MOM, Z_STOP, cost_bps=0.0
                    )
                    
                    event = {
                        'symbol': name,
                        'timestamp': ts[i],
                        'strategy_type': 'MOM',
                        'direction': direction,
                        'active_leg': active_asset,
                        'entry_idx': i,
                        'entry_z': z,
                        'exit_idx': i + duration,
                        'pnl_bps': pnl,
                        'duration': duration,
                        'outcome': outcome,
                        'z_accel': acc
                    }
                    all_events.append(event)
                    last_entry_mom = i

            # === REVERSION TRADE ===
            # (Keeping reversion for completeness, though we focus on MOM)
            if abs(z) > Z_ENTRY_REV and (i - last_entry_rev > min_gap):
                 pass # Skipping REV for now to save time/space as we are focused on MOM optimization

    # Phase 3: Save
    print(f"\nPhase 3: Saving {len(all_events)} events...")
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_h4_8yr_v3_dual.csv")
        df_out.write_csv(out_path)
        print(f"Saved to {out_path}")

        # Split datasets (Only MOM populated)
        df_mom = df_out.filter(pl.col("strategy_type") == "MOM")
        out_mom = os.path.join(OUTPUT_DIR, "events_h4_8yr_v3_mom.csv")
        df_mom.write_csv(out_mom)
        print(f"Saved split dataset:\n- {out_mom}")
        
    else:
        print("No events found.")


if __name__ == "__main__":  # pragma: no cover
    build_dataset()
