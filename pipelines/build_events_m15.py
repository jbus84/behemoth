#!/usr/bin/env python3
"""
Event dataset builder (M15).
Generates MOM/REV trades for analysis; production strategy is MOM-only.
"""

import os
import sys
from collections import defaultdict

import numpy as np
import polars as pl

sys.path.append(os.path.join(os.getcwd(), "src"))
from behemoth.config import (
    Z_ENTRY_MOM,
    Z_ENTRY_REV,
    Z_STOP,
    MIN_GAP_BARS,
    ACTIVE_LEG_LOW,
    ACTIVE_LEG_HIGH,
)
from behemoth.core.active_leg import select_active_leg
from behemoth.core.events import simulate_trade as _simulate_trade
from behemoth.core.kalman import compute_kalman_states as _compute_kalman_states
from behemoth.core.zscore import compute_z_scores as _compute_z_scores
from behemoth.io.loaders import load_pair_data as _load_pair_data

DATA_DIR = "data/global_15m"
OUTPUT_DIR = "data/events"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === PAIR UNIVERSE ===
PAIRS = [
    # FX & Commodities
    ("EUR/GBP", "EURUSD_15m.parquet", "GBPUSD_15m.parquet", "close_EURUSD", "close_GBPUSD", 1.6, 1.0),
    ("Gold/Oil", "BCOUSD_15m.parquet", "XAUUSD_15m.parquet", "close_BCOUSD", "close_XAUUSD", 3.0, 3.0),
    ("Oil/Silver", "BCOUSD_15m.parquet", "XAGUSD_15m.parquet", "close_BCOUSD", "close_XAGUSD", 3.0, 3.0),
    ("AUD/NZD", "NZDUSD_15m.parquet", "AUDUSD_15m.parquet", "close_NZDUSD", "close_AUDUSD", 2.0, 2.0),
    ("CAC/NZD", "NZDUSD_15m.parquet", "FRXEUR_15m.parquet", "close_NZDUSD", "close_FRXEUR", 3.0, 3.0),
    ("Gold/Silver", "XAUUSD_15m.parquet", "XAGUSD_15m.parquet", "close_XAUUSD", "close_XAGUSD", 3.0, 3.0),
    # Global Equities
    ("SPX/DAX", "SPXUSD_15m.parquet", "GRXEUR_15m.parquet", "close_SPXUSD", "close_GRXEUR", 3.0, 2.0),
    ("SPX/CAC", "SPXUSD_15m.parquet", "FRXEUR_15m.parquet", "close_SPXUSD", "close_FRXEUR", 3.0, 2.0),
    ("SPX/FTSE", "SPXUSD_15m.parquet", "UKXGBP_15m.parquet", "close_SPXUSD", "close_UKXGBP", 3.0, 2.0),
    ("SPX/Nikkei", "SPXUSD_15m.parquet", "JPXJPY_15m.parquet", "close_SPXUSD", "close_JPXJPY", 3.0, 2.0),
    ("SPX/HK", "SPXUSD_15m.parquet", "HKXHKD_15m.parquet", "close_SPXUSD", "close_HKXHKD", 4.0, 2.0),
    ("SPX/Dow", "SPXUSD_15m.parquet", "UDXUSD_15m.parquet", "close_SPXUSD", "close_UDXUSD", 2.0, 2.0),
    ("SPX/Nas", "SPXUSD_15m.parquet", "NSXUSD_15m.parquet", "close_SPXUSD", "close_NSXUSD", 2.0, 2.0),
    # Extended FX
    ("AUD/CAD", "AUDUSD_15m.parquet", "USDCAD_15m.parquet", "close_AUDUSD", "close_USDCAD", 2.0, 2.0),
    ("EUR/CHF", "EURUSD_15m.parquet", "USDCHF_15m.parquet", "close_EURUSD", "close_USDCHF", 2.0, 2.0),
    ("EUR/JPY", "EURUSD_15m.parquet", "USDJPY_15m.parquet", "close_EURUSD", "close_USDJPY", 2.0, 1.0),
    ("GBP/JPY", "GBPUSD_15m.parquet", "USDJPY_15m.parquet", "close_GBPUSD", "close_USDJPY", 2.0, 1.0),
    ("CHF/JPY", "USDCHF_15m.parquet", "USDJPY_15m.parquet", "close_USDCHF", "close_USDJPY", 2.0, 1.0),
    ("EUR/AUD", "EURUSD_15m.parquet", "AUDUSD_15m.parquet", "close_EURUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/AUD", "GBPUSD_15m.parquet", "AUDUSD_15m.parquet", "close_GBPUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/CAD", "GBPUSD_15m.parquet", "USDCAD_15m.parquet", "close_GBPUSD", "close_USDCAD", 2.0, 2.0),
    ("NZD/CAD", "NZDUSD_15m.parquet", "USDCAD_15m.parquet", "close_NZDUSD", "close_USDCAD", 2.0, 2.0),
]

def load_pair_data(fx, fy, cx, cy):
    return _load_pair_data(DATA_DIR, fx, fy, cx, cy)


def compute_kalman_states(y, x):
    return _compute_kalman_states(y, x)


def compute_z_scores(errors, window=500):
    return _compute_z_scores(errors, window=window)


def simulate_trade(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh=1.5, stop=3.5):
    return _simulate_trade(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh, stop)



def build_dataset():  # pragma: no cover
    print("--- BUILDING EVENT DATASET (M15, MOM/REV) ---")

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

        pair_states[name] = {
            'y': y, 'x': x, 'ts': ts,
            'betas': betas, 'errors': errors, 'ret_betas': ret_betas, 'z_scores': z_scores,
            'cost_y': cost_y, 'cost_x': cost_x
        }
        print(f"  {name}: {len(y)} bars")

    # Phase 2: Generate BOTH strategy types for each signal
    print("\nPhase 2: Generating dual-strategy events...")
    all_events = []
    pair_trade_history = defaultdict(lambda: {'MOM': [], 'REV': []})

    for name, state in pair_states.items():
        print(f"  Processing {name}...")

        y, x, ts = state['y'], state['x'], state['ts']
        betas, errors, ret_betas, z_scores = state['betas'], state['errors'], state['ret_betas'], state['z_scores']
        cost_y, cost_x = state['cost_y'], state['cost_x']

        # Track last entry to avoid overlapping trades
        last_entry_mom = 0
        last_entry_rev = 0
        min_gap = MIN_GAP_BARS

        for i in range(500, len(y) - 500):
            z = z_scores[i]
            beta = betas[i]

            # Determine active asset based on Whip/Tank
            active_asset = select_active_leg(beta, ACTIVE_LEG_LOW, ACTIVE_LEG_HIGH)
            if active_asset == "Y":
                cost = cost_y
            elif active_asset == "X":
                cost = cost_x
            else:
                continue  # Skip neutral zone

            # Check for signal
            if abs(z) < min_thresh:
                continue

            # === MOMENTUM TRADE ===
            if i - last_entry_mom >= min_gap and abs(z) >= thresh_mom:
                if z > 0:
                    mom_dir = 1  # Long (follow the trend up)
                else:
                    mom_dir = -1  # Short (follow the trend down)

                pnl, duration, outcome = simulate_trade(
                    i, mom_dir, 'MOM', y, x, z_scores, active_asset, thresh_mom, stop_level
                )

                # Rolling performance
                history = pair_trade_history[name]['MOM']
                if len(history) >= 10:
                    rolling_wr = sum(1 for p in history[-10:] if p > 0) / 10
                    rolling_pnl = np.mean(history[-10:])
                else:
                    rolling_wr = 0.5
                    rolling_pnl = 0.0

                row = {
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(str(ts[i])[:4]),
                    "strategy_type": "MOM",
                    "active_leg": active_asset,
                    "side": "LONG" if mom_dir == 1 else "SHORT",
                    "outcome": outcome,
                    "pnl_bps": round(pnl, 2),
                    "duration_bars": duration,
                    "rolling_win_rate_10": round(rolling_wr, 2),
                    "rolling_avg_pnl_10": round(rolling_pnl, 2),
                }
                all_events.append(row)
                pair_trade_history[name]['MOM'].append(pnl)
                last_entry_mom = i

            # === REVERSION TRADE ===
            if i - last_entry_rev >= min_gap and abs(z) >= thresh_rev:
                if z > 0:
                    rev_dir = -1  # Short (fade the move, expect reversion)
                else:
                    rev_dir = 1  # Long (fade the move, expect reversion)

                pnl, duration, outcome = simulate_trade(
                    i, rev_dir, 'REV', y, x, z_scores, active_asset, thresh_rev, stop_level
                )

                # Rolling performance
                history = pair_trade_history[name]['REV']
                if len(history) >= 10:
                    rolling_wr = sum(1 for p in history[-10:] if p > 0) / 10
                    rolling_pnl = np.mean(history[-10:])
                else:
                    rolling_wr = 0.5
                    rolling_pnl = 0.0

                row = {
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(str(ts[i])[:4]),
                    "strategy_type": "REV",
                    "active_leg": active_asset,
                    "side": "LONG" if rev_dir == 1 else "SHORT",
                    "outcome": outcome,
                    "pnl_bps": round(pnl, 2),
                    "duration_bars": duration,
                    "rolling_win_rate_10": round(rolling_wr, 2),
                    "rolling_avg_pnl_10": round(rolling_pnl, 2),
                }
                all_events.append(row)
                pair_trade_history[name]['REV'].append(pnl)
                last_entry_rev = i

    # Phase 3: Save
    print(f"\nPhase 3: Saving {len(all_events)} events...")
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_m15_8yr_v3_dual.csv")
        df_out.write_csv(out_path)
        print(f"Saved to {out_path}")

        # Split datasets
        df_mom = df_out.filter(pl.col("strategy_type") == "MOM")
        df_rev = df_out.filter(pl.col("strategy_type") == "REV")
        out_mom = os.path.join(OUTPUT_DIR, "events_m15_8yr_v3_mom.csv")
        out_rev = os.path.join(OUTPUT_DIR, "events_m15_8yr_v3_rev.csv")
        df_mom.write_csv(out_mom)
        df_rev.write_csv(out_rev)
        print(f"Saved split datasets:\n- {out_mom}\n- {out_rev}")

        # Summary
        print("\n=== DATASET SUMMARY ===")
        print(f"Total Events: {len(all_events)}")

        mom_events = [e for e in all_events if e['strategy_type'] == 'MOM']
        rev_events = [e for e in all_events if e['strategy_type'] == 'REV']

        mom_pnl = [e['pnl_bps'] for e in mom_events]
        rev_pnl = [e['pnl_bps'] for e in rev_events]

        print(f"\nMOMENTUM: {len(mom_events)} trades")
        print(f"  Mean: {np.mean(mom_pnl):.2f} | Median: {np.median(mom_pnl):.2f} | P5: {np.percentile(mom_pnl, 5):.2f} | P95: {np.percentile(mom_pnl, 95):.2f}")

        print(f"\nREVERSION: {len(rev_events)} trades")
        print(f"  Mean: {np.mean(rev_pnl):.2f} | Median: {np.median(rev_pnl):.2f} | P5: {np.percentile(rev_pnl, 5):.2f} | P95: {np.percentile(rev_pnl, 95):.2f}")

        # By pair and strategy
        print("\n=== BY PAIR & STRATEGY ===")
        for pair in pair_states.keys():
            pair_mom = [e['pnl_bps'] for e in all_events if e['pair'] == pair and e['strategy_type'] == 'MOM']
            pair_rev = [e['pnl_bps'] for e in all_events if e['pair'] == pair and e['strategy_type'] == 'REV']
            if pair_mom and pair_rev:
                print(f"{pair}:")
                print(f"  MOM: n={len(pair_mom)}, mean={np.mean(pair_mom):.2f}, med={np.median(pair_mom):.2f}, p5={np.percentile(pair_mom, 5):.2f}, p95={np.percentile(pair_mom, 95):.2f}")
                print(f"  REV: n={len(pair_rev)}, mean={np.mean(pair_rev):.2f}, med={np.median(pair_rev):.2f}, p5={np.percentile(pair_rev, 5):.2f}, p95={np.percentile(pair_rev, 95):.2f}")
    else:
        print("No events found.")


if __name__ == "__main__":  # pragma: no cover
    build_dataset()
