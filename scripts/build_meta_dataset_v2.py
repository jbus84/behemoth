#!/usr/bin/env python3
"""
Meta Model Dataset Generator v2
Comprehensive feature engineering for M15 Kalman arbitrage signals.
"""

import polars as pl
import numpy as np
import os
import sys
from datetime import datetime
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"
OUTPUT_DIR = "data/meta_model"
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
    """Load and join pair data for 8 years."""
    try:
        p_x = os.path.join(DATA_DIR, fx)
        p_y = os.path.join(DATA_DIR, fy)
        df_x = pl.read_parquet(p_x).rename({cx: "X"})
        df_y = pl.read_parquet(p_y).rename({cy: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {fx}/{fy}: {e}")
        return None

def compute_kalman_states(y, x):
    """Compute Kalman filter states for the full series."""
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    errors = []
    
    for i in range(len(y)):
        if i < 10:
            mu_y, mu_x = y[i], x[i]
        else:
            mu_y = np.mean(y[max(0, i-500):i])
            mu_x = np.mean(x[max(0, i-500):i])
        b, _ = kf.update(x[i] - mu_x, y[i] - mu_y)
        betas.append(b)
        errors.append((y[i] - mu_y) - b * (x[i] - mu_x))
    
    return np.array(betas), np.array(errors)

def compute_z_scores(errors, window=500):
    """Compute rolling Z-scores."""
    z_scores = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i-window:i]
        mu, std = np.mean(window_data), np.std(window_data)
        if std > 1e-6:
            z_scores[i] = (errors[i] - mu) / std
    return z_scores

def compute_features_at_entry(i, y, x, betas, errors, z_scores, ts):
    """Compute all features at entry index i."""
    features = {}
    
    # === 1. Signal Quality ===
    # Z-score at entry
    features['z_entry'] = round(z_scores[i], 2)
    
    # Z-velocity (5-bar change)
    prev_i = max(500, i - 5)
    features['z_velocity'] = round(z_scores[i] - z_scores[prev_i], 2)
    
    # Spread std (volatility of spread residuals)
    features['spread_std'] = round(np.std(errors[max(0, i-500):i]) * 10000, 2)  # in bps
    
    # Beta stability (std of beta over 100 bars)
    features['beta_stability'] = round(np.std(betas[max(0, i-100):i]), 4)
    
    # === 2. Market Regime ===
    features['beta'] = round(betas[i], 4)
    
    # Volatility ratio
    start = max(0, i - 500)
    vol_y = np.std(np.diff(y[start:i]))
    vol_x = np.std(np.diff(x[start:i]))
    features['vol_ratio'] = round(vol_y / vol_x if vol_x > 0 else 1.0, 3)
    
    # Rolling correlation
    if i >= 500:
        corr = np.corrcoef(x[i-500:i], y[i-500:i])[0, 1]
        features['correlation_500'] = round(corr, 3)
    else:
        features['correlation_500'] = 0.0
    
    # Trend strength (slope of spread normalized by std)
    if i >= 100:
        spread = y[i-100:i] - betas[i] * x[i-100:i]
        slope = np.polyfit(np.arange(100), spread, 1)[0]
        features['trend_strength'] = round(slope / (np.std(spread) + 1e-8), 3)
    else:
        features['trend_strength'] = 0.0
    
    # === 3. Time Context ===
    entry_ts = ts[i]
    if hasattr(entry_ts, 'hour'):
        features['hour'] = entry_ts.hour
        features['day_of_week'] = entry_ts.weekday()
    else:
        # Handle numpy datetime64
        dt = np.datetime64(entry_ts, 'ns').astype('datetime64[s]').astype(datetime)
        features['hour'] = dt.hour
        features['day_of_week'] = dt.weekday()
    
    # === 4. Technical Context ===
    # 4-hour returns (16 bars)
    lookback = min(i, 16)
    features['ret_X_4h'] = round((x[i] - x[i - lookback]) * 10000, 2)
    features['ret_Y_4h'] = round((y[i] - y[i - lookback]) * 10000, 2)
    
    # ATR ratio (approximated with range of last 100 bars)
    if i >= 100:
        atr_y = np.mean([max(y[j:j+4]) - min(y[j:j+4]) for j in range(i-100, i, 4)])
        atr_x = np.mean([max(x[j:j+4]) - min(x[j:j+4]) for j in range(i-100, i, 4)])
        features['atr_ratio'] = round(atr_y / atr_x if atr_x > 0 else 1.0, 3)
    else:
        features['atr_ratio'] = 1.0
    
    return features

def build_dataset():
    print("--- BUILDING META MODEL DATASET v2 (FULL FEATURES) ---")
    
    thresh = 1.5
    stop_level = 3.5
    
    # === PHASE 1: Compute all Z-scores for cross-pair signals ===
    print("Phase 1: Computing Kalman states for all pairs...")
    pair_states = {}  # {pair_name: {'z': z_scores, 'ts': timestamps}}
    
    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
        
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        betas, errors = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        pair_states[name] = {
            'y': y, 'x': x, 'ts': ts,
            'betas': betas, 'errors': errors, 'z_scores': z_scores,
            'cost_y': cost_y, 'cost_x': cost_x
        }
        print(f"  {name}: {len(y)} bars")
    
    # === PHASE 2: Generate events with full features ===
    print("\nPhase 2: Generating events with full features...")
    all_events = []
    pair_trade_history = defaultdict(list)  # For rolling performance features
    
    for name, state in pair_states.items():
        print(f"  Processing {name}...")
        
        y, x, ts = state['y'], state['x'], state['ts']
        betas, errors, z_scores = state['betas'], state['errors'], state['z_scores']
        cost_y, cost_x = state['cost_y'], state['cost_x']
        
        in_pos = 0
        active_asset = None
        entry_price = 0.0
        entry_idx = 0
        
        for i in range(500, len(y)):
            beta = betas[i]
            z = z_scores[i]
            
            # Regime logic
            if beta < 0.98:
                target_asset = 'Y'
            elif beta > 1.02:
                target_asset = 'X'
            else:
                target_asset = 'NEUTRAL'
            
            # Entry
            if in_pos == 0:
                if target_asset == 'Y':
                    if z > thresh:
                        in_pos = 1
                        active_asset = 'Y'
                        entry_price = y[i]
                        entry_idx = i
                    elif z < -thresh:
                        in_pos = -1
                        active_asset = 'Y'
                        entry_price = y[i]
                        entry_idx = i
                elif target_asset == 'X':
                    if z > thresh:
                        in_pos = -1
                        active_asset = 'X'
                        entry_price = x[i]
                        entry_idx = i
                    elif z < -thresh:
                        in_pos = 1
                        active_asset = 'X'
                        entry_price = x[i]
                        entry_idx = i
            
            # Exit
            elif in_pos != 0:
                closed = False
                pnl = 0.0
                outcome = ""
                
                curr_y, curr_x = y[i], x[i]
                
                if active_asset == 'Y':
                    if in_pos == 1:
                        if z < 0:
                            pnl = (curr_y - entry_price) * 10000 - cost_y
                            closed = True
                            outcome = "LOSS_REV"
                        elif z > stop_level:
                            pnl = (curr_y - entry_price) * 10000 - cost_y
                            closed = True
                            outcome = "WIN_MOM"
                    elif in_pos == -1:
                        if z > 0:
                            pnl = -(curr_y - entry_price) * 10000 - cost_y
                            closed = True
                            outcome = "LOSS_REV"
                        elif z < -stop_level:
                            pnl = -(curr_y - entry_price) * 10000 - cost_y
                            closed = True
                            outcome = "WIN_MOM"
                elif active_asset == 'X':
                    if in_pos == -1:
                        if z < 0:
                            pnl = -(curr_x - entry_price) * 10000 - cost_x
                            closed = True
                            outcome = "LOSS_REV"
                        elif z > stop_level:
                            pnl = -(curr_x - entry_price) * 10000 - cost_x
                            closed = True
                            outcome = "WIN_MOM"
                    elif in_pos == 1:
                        if z > 0:
                            pnl = (curr_x - entry_price) * 10000 - cost_x
                            closed = True
                            outcome = "LOSS_REV"
                        elif z < -stop_level:
                            pnl = (curr_x - entry_price) * 10000 - cost_x
                            closed = True
                            outcome = "WIN_MOM"
                
                if closed:
                    # Compute features at entry
                    features = compute_features_at_entry(
                        entry_idx, y, x, betas, errors, z_scores, ts
                    )
                    
                    # === 4. Recent Performance (rolling) ===
                    history = pair_trade_history[name]
                    if len(history) >= 10:
                        recent = history[-10:]
                        features['rolling_win_rate_10'] = round(
                            sum(1 for p in recent if p > 0) / 10, 2
                        )
                        features['rolling_avg_pnl_10'] = round(np.mean(recent), 2)
                    else:
                        features['rolling_win_rate_10'] = 0.5  # neutral prior
                        features['rolling_avg_pnl_10'] = 0.0
                    
                    # === 6. Cross-Pair Signals ===
                    # Count pairs with |z| > 1.5 at entry time
                    entry_ts = ts[entry_idx]
                    num_active = 0
                    for other_name, other_state in pair_states.items():
                        if other_name == name:
                            continue
                        # Find closest index by timestamp
                        ts_diff = np.abs(other_state['ts'] - entry_ts)
                        closest_idx = np.argmin(ts_diff)
                        if closest_idx >= 500:
                            other_z = other_state['z_scores'][closest_idx]
                            if abs(other_z) > 1.5:
                                num_active += 1
                    features['num_active_signals'] = num_active
                    
                    # Build row
                    row = {
                        "pair": name,
                        "timestamp": ts[entry_idx],
                        "year": int(str(ts[entry_idx])[:4]),
                        "active_leg": active_asset,
                        "side": "LONG" if in_pos == 1 else "SHORT",
                        "outcome": outcome,
                        "pnl_bps": round(pnl, 2),
                        "duration_bars": i - entry_idx,
                        **features
                    }
                    all_events.append(row)
                    
                    # Track for rolling performance
                    pair_trade_history[name].append(pnl)
                    
                    in_pos = 0
                    active_asset = None
    
    # === PHASE 3: Save ===
    print(f"\nPhase 3: Saving {len(all_events)} events...")
    if len(all_events) > 0:
        df_out = pl.DataFrame(all_events)
        out_path = os.path.join(OUTPUT_DIR, "events_m15_8yr_v2.csv")
        df_out.write_csv(out_path)
        print(f"Saved to {out_path}")
        
        # Summary
        print("\n=== DATASET SUMMARY ===")
        print(f"Total Events: {len(all_events)}")
        print(f"Features: {list(all_events[0].keys())}")
        print(f"Pairs: {len(pair_states)}")
        
        # PnL by pair
        print("\nPnL by Pair:")
        for pair in pair_states.keys():
            pair_events = [e for e in all_events if e['pair'] == pair]
            if pair_events:
                avg_pnl = np.mean([e['pnl_bps'] for e in pair_events])
                print(f"  {pair}: {len(pair_events)} trades, {avg_pnl:.2f} avg bps")
    else:
        print("No events found.")

if __name__ == "__main__":
    build_dataset()
