#!/usr/bin/env python3
"""
Event dataset builder (H1).
Generates MOM/REV trades for analysis based on 1-Hour candles.
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
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from behemoth.config import (
    Z_ENTRY_MOM,
    Z_ENTRY_REV,
    Z_STOP,
    MIN_GAP_BARS,
    ACTIVE_LEG_LOW,
    ACTIVE_LEG_HIGH,
    MOM_ACCEL_THRESH,
    REV_ACCEL_THRESH,
    EXIT_TIMEOUT_MODE_OFFLINE,
    ENTRY_EXIT_VARIANTS,
)
from behemoth.core.active_leg import select_active_leg
from behemoth.core.exit_contract import build_exit_contract
from behemoth.core.events import simulate_trade as _simulate_trade
from behemoth.core.kalman import compute_kalman_states as _compute_kalman_states
from behemoth.core.zscore import compute_z_scores as _compute_z_scores
from behemoth.io.loaders import load_pair_data as _load_pair_data

DATA_DIR = "data/global_1h"
OUTPUT_DIR = "data/events"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === PAIR UNIVERSE ===
# Note: Input files are now named '{SYM}_1h.parquet' and contain a 'close' column.
# We map the generic 'close' column to X/Y using the loader's renaming feature.
# Format: (Name, FileY, FileX, ColY, ColX, CostY, CostX)
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
    # Ensure correct mapping. 
    # cx is name of column in FileX to rename to "X"
    # cy is name of column in FileY to rename to "Y"
    return _load_pair_data(DATA_DIR, fx, fy, cx, cy)


def compute_kalman_states(y, x):
    return _compute_kalman_states(y, x)


def compute_z_scores(errors, window=750):
    return _compute_z_scores(errors, window=window)


def simulate_trade(
    entry_idx,
    direction,
    strategy_type,
    y,
    x,
    z_scores,
    active_asset,
    thresh=1.5,
    stop=3.5,
    exit_contract=None,
):
    return _simulate_trade(
        entry_idx,
        direction,
        strategy_type,
        y,
        x,
        z_scores,
        active_asset,
        thresh,
        stop,
        exit_contract=exit_contract,
    )



def build_dataset():  # pragma: no cover
    print("--- BUILDING EVENT DATASET (H1, MOM/REV) ---")

    thresh_mom = Z_ENTRY_MOM
    thresh_rev = Z_ENTRY_REV
    stop_level = Z_STOP
    min_thresh = min(thresh_mom, thresh_rev)

    # Phase 1: Load all data
    print("Phase 1: Loading data and computing Kalman states...")
    pair_states = {}

    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

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
        print(f"  {name}: {len(y)} bars")

    # Phase 2: Generate BOTH strategy types for each signal
    print("\nPhase 2: Generating dual-strategy events...")
    all_events = []
    entry_exit_variants = list(ENTRY_EXIT_VARIANTS)
    pair_trade_history = defaultdict(
        lambda: {v: {'MOM': [], 'REV': []} for v in entry_exit_variants}
    )

    for name, state in pair_states.items():
        print(f"  Processing {name}...")

        y, x, ts = state['y'], state['x'], state['ts']
        betas, errors, ret_betas, z_scores = state['betas'], state['errors'], state['ret_betas'], state['z_scores']
        z_accel = state['z_accel']
        cost_y, cost_x = state['cost_y'], state['cost_x']

        # Track last entry to avoid overlapping trades (independent per exit variant)
        last_entry_mom = {v: 0 for v in entry_exit_variants}
        last_entry_rev = {v: 0 for v in entry_exit_variants}
        min_gap = MIN_GAP_BARS

        for i in range(500, len(y) - 500):
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

            for entry_exit_variant in entry_exit_variants:
                # === MOMENTUM TRADE ===
                # Condition: Z > Entry AND Accel > Thresh (Trend Confirmation)
                if abs(z) > Z_ENTRY_MOM and (i - last_entry_mom[entry_exit_variant] > min_gap):
                    if acc > MOM_ACCEL_THRESH: # Filter: Must obey Acceleration
                        if z > 0:
                            direction = 1  # Long Spread (Trend Continuing Up)
                        else:
                            direction = -1 # Short Spread (Trend Continuing Down)

                        exit_contract = build_exit_contract(
                            timeframe="m60",
                            entry_z=float(z),
                            timeout_mode=EXIT_TIMEOUT_MODE_OFFLINE,
                            variant=entry_exit_variant,
                            z_stop=Z_STOP,
                        )
                        pnl, duration, outcome = _simulate_trade(
                            i,
                            direction,
                            "MOM",
                            y,
                            x,
                            z_scores,
                            active_asset,
                            Z_ENTRY_MOM,
                            Z_STOP,
                            cost_bps=0.0,
                            exit_contract=exit_contract,
                        )

                        # Store Event
                        event = {
                            'symbol': name,
                            'timestamp': str(ts[i]),
                            'strategy_type': 'MOM',
                            'entry_exit_variant': entry_exit_variant,
                            'exit_policy': exit_contract.mode,
                            'max_hold_bars': int(exit_contract.max_hold_bars),
                            'entry_cross_zero_level': float(exit_contract.cross_zero_buffer_abs_z),
                            'entry_stop_win_level_abs_z': float(exit_contract.stop_win_level_abs_z),
                            'entry_use_stop_win': bool(exit_contract.use_stop_win),
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
                        pair_trade_history[name][entry_exit_variant]['MOM'].append(event)
                        last_entry_mom[entry_exit_variant] = i

                # === REVERSION TRADE ===
                # Condition: Z > Entry AND Accel < Thresh (Trend Exhaustion)
                if abs(z) > Z_ENTRY_REV and (i - last_entry_rev[entry_exit_variant] > min_gap):
                    if acc < REV_ACCEL_THRESH: # Filter: Must obey Deceleration
                        if z > 0:
                            direction = -1 # Short Spread (Betting on Reversion)
                        else:
                            direction = 1  # Long Spread

                        exit_contract = build_exit_contract(
                            timeframe="m60",
                            entry_z=float(z),
                            timeout_mode=EXIT_TIMEOUT_MODE_OFFLINE,
                            variant=entry_exit_variant,
                            z_stop=Z_STOP,
                        )
                        pnl, duration, outcome = _simulate_trade(
                            i,
                            direction,
                            "REV",
                            y,
                            x,
                            z_scores,
                            active_asset,
                            Z_ENTRY_REV,
                            Z_STOP,
                            cost_bps=0.0,
                            exit_contract=exit_contract,
                        )

                        event = {
                            'symbol': name,
                            'timestamp': str(ts[i]),
                            'strategy_type': 'REV',
                            'entry_exit_variant': entry_exit_variant,
                            'exit_policy': exit_contract.mode,
                            'max_hold_bars': int(exit_contract.max_hold_bars),
                            'entry_cross_zero_level': float(exit_contract.cross_zero_buffer_abs_z),
                            'entry_stop_win_level_abs_z': float(exit_contract.stop_win_level_abs_z),
                            'entry_use_stop_win': bool(exit_contract.use_stop_win),
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
                        pair_trade_history[name][entry_exit_variant]['REV'].append(event)
                        last_entry_rev[entry_exit_variant] = i

    # Phase 3: Save
    print(f"\nPhase 3: Saving {len(all_events)} events...")
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_h1_8yr_v3_dual.csv")
        df_out.write_csv(out_path)
        print(f"Saved to {out_path}")

        # Split datasets
        df_mom = df_out.filter(pl.col("strategy_type") == "MOM")
        df_rev = df_out.filter(pl.col("strategy_type") == "REV")
        out_mom = os.path.join(OUTPUT_DIR, "events_h1_8yr_v3_mom.csv")
        out_rev = os.path.join(OUTPUT_DIR, "events_h1_8yr_v3_rev.csv")
        df_mom.write_csv(out_mom)
        df_rev.write_csv(out_rev)
        print(f"Saved split datasets:\n- {out_mom}\n- {out_rev}")

        # Summary
        print("\n=== DATASET SUMMARY ===")
        print(f"Total Events: {len(all_events)}")
        
        # ... (Same summary logic as M15) ...
    else:
        print("No events found.")


if __name__ == "__main__":  # pragma: no cover
    build_dataset()
