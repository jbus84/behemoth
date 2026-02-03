#!/usr/bin/env python3
"""
Meta Model Dataset Generator v3
DUAL STRATEGY: Generate BOTH Momentum AND Reversion trades for each signal.
Model learns which strategy works for which pair/regime.
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
    z_scores = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i-window:i]
        mu, std = np.mean(window_data), np.std(window_data)
        if std > 1e-6:
            z_scores[i] = (errors[i] - mu) / std
    return z_scores

def compute_features_at_entry(i, y, x, betas, errors, z_scores, ts):
    features = {}
    
    # Signal Quality
    features['z_entry'] = round(z_scores[i], 2)
    prev_i = max(500, i - 5)
    features['z_velocity'] = round(z_scores[i] - z_scores[prev_i], 2)
    features['spread_std'] = round(np.std(errors[max(0, i-500):i]) * 10000, 2)
    features['beta_stability'] = round(np.std(betas[max(0, i-100):i]), 4)
    
    # Market Regime
    features['beta'] = round(betas[i], 4)
    start = max(0, i - 500)
    vol_y = np.std(np.diff(y[start:i]))
    vol_x = np.std(np.diff(x[start:i]))
    features['vol_ratio'] = round(vol_y / vol_x if vol_x > 0 else 1.0, 3)
    
    if i >= 500:
        corr = np.corrcoef(x[i-500:i], y[i-500:i])[0, 1]
        features['correlation_500'] = round(corr, 3)
    else:
        features['correlation_500'] = 0.0
    
    if i >= 100:
        spread = y[i-100:i] - betas[i] * x[i-100:i]
        slope = np.polyfit(np.arange(100), spread, 1)[0]
        features['trend_strength'] = round(slope / (np.std(spread) + 1e-8), 3)
    else:
        features['trend_strength'] = 0.0
    
    # Time Context
    entry_ts = ts[i]
    if hasattr(entry_ts, 'hour'):
        features['hour'] = entry_ts.hour
        features['day_of_week'] = entry_ts.weekday()
    else:
        dt = np.datetime64(entry_ts, 'ns').astype('datetime64[s]').astype(datetime)
        features['hour'] = dt.hour
        features['day_of_week'] = dt.weekday()
    
    # Technical Context
    lookback = min(i, 16)
    features['ret_X_4h'] = round((x[i] - x[i - lookback]) * 10000, 2)
    features['ret_Y_4h'] = round((y[i] - y[i - lookback]) * 10000, 2)
    
    if i >= 100:
        atr_y = np.mean([max(y[j:j+4]) - min(y[j:j+4]) for j in range(i-100, i, 4)])
        atr_x = np.mean([max(x[j:j+4]) - min(x[j:j+4]) for j in range(i-100, i, 4)])
        features['atr_ratio'] = round(atr_y / atr_x if atr_x > 0 else 1.0, 3)
    else:
        features['atr_ratio'] = 1.0
    
    # Barrier Context Features (historical, no leakage)
    # Entry ATR: volatility of last 50 bars (used for hypothetical barrier sizing)
    if i >= 50:
        recent_returns = np.diff(y[i-50:i])
        features['entry_atr'] = round(np.std(recent_returns) * 10000, 2)  # in bps
    else:
        features['entry_atr'] = 0.0
    
    # Vol Regime: Is current vol high or low vs long-term average?
    if i >= 500:
        short_vol = np.std(np.diff(y[i-50:i]))
        long_vol = np.std(np.diff(y[i-500:i]))
        features['vol_regime'] = round(short_vol / long_vol if long_vol > 0 else 1.0, 2)
    else:
        features['vol_regime'] = 1.0
    
    return features

def simulate_trade(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh=1.5, stop=3.5):
    """
    Simulate a single trade with Z-SCORE EXITS ONLY.
    Barriers are recorded as features, not used for exits.
    """
    prices = y if active_asset == 'Y' else x
    entry_price = prices[entry_idx]
    
    for i in range(entry_idx + 1, min(entry_idx + 500, len(z_scores))):
        z = z_scores[i]
        curr_price = prices[i]
        
        if strategy_type == 'MOM':
            if direction == 1:  # Long
                if z < 0:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'LOSS_REV'
                elif z > stop:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'WIN_MOM'
            else:  # Short
                if z > 0:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'LOSS_REV'
                elif z < -stop:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'WIN_MOM'
        
        else:  # REVERSION
            if direction == 1:  # Long
                if z > 0:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'WIN_REV'
                elif z < -stop:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'LOSS_MOM'
            else:  # Short
                if z < 0:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'WIN_REV'
                elif z > stop:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, 'LOSS_MOM'
    
    # Timeout
    curr_price = prices[min(entry_idx + 499, len(prices)-1)]
    if direction == 1:
        pnl = (curr_price - entry_price) * 10000
    else:
        pnl = -(curr_price - entry_price) * 10000
    return pnl, 500, 'TIMEOUT'



def build_dataset():
    print("--- BUILDING META MODEL DATASET v3 (DUAL STRATEGY) ---")
    
    thresh = 1.5
    stop_level = 3.5
    
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
        
        betas, errors = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        
        pair_states[name] = {
            'y': y, 'x': x, 'ts': ts,
            'betas': betas, 'errors': errors, 'z_scores': z_scores,
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
        betas, errors, z_scores = state['betas'], state['errors'], state['z_scores']
        cost_y, cost_x = state['cost_y'], state['cost_x']
        
        # Track last entry to avoid overlapping trades
        last_entry_mom = 0
        last_entry_rev = 0
        min_gap = 20  # Minimum bars between trades
        
        for i in range(500, len(y) - 500):
            z = z_scores[i]
            beta = betas[i]
            
            # Determine active asset based on Whip/Tank
            if beta < 0.98:
                active_asset = 'Y'
                cost = cost_y
            elif beta > 1.02:
                active_asset = 'X'
                cost = cost_x
            else:
                continue  # Skip neutral zone
            
            # Check for signal
            if abs(z) < thresh:
                continue
            
            # Compute features at entry
            features = compute_features_at_entry(i, y, x, betas, errors, z_scores, ts)
            
            # Cross-pair signals: SKIPPED for performance
            features['num_active_signals'] = 0
            
            # === MOMENTUM TRADE ===
            if i - last_entry_mom >= min_gap:
                if z > thresh:
                    mom_dir = 1  # Long (follow the trend up)
                else:
                    mom_dir = -1  # Short (follow the trend down)
                
                pnl, duration, outcome = simulate_trade(
                    i, mom_dir, 'MOM', y, x, z_scores, active_asset, thresh, stop_level
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
                    **features
                }
                all_events.append(row)
                pair_trade_history[name]['MOM'].append(pnl)
                last_entry_mom = i
            
            # === REVERSION TRADE ===
            if i - last_entry_rev >= min_gap:
                if z > thresh:
                    rev_dir = -1  # Short (fade the move, expect reversion)
                else:
                    rev_dir = 1  # Long (fade the move, expect reversion)
                
                pnl, duration, outcome = simulate_trade(
                    i, rev_dir, 'REV', y, x, z_scores, active_asset, thresh, stop_level
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
                    **features
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


if __name__ == "__main__":
    build_dataset()
