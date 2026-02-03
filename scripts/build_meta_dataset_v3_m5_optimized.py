#!/usr/bin/env python3
"""
Optimized 5M Meta Model Dataset Generator
Vectorized Z-Score and Safety Checks
"""

import polars as pl
import numpy as np
import pandas as pd
import os
import sys
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_5m"
OUTPUT_DIR = "data/meta_model"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Define PAIRS with 5m suffixes
PAIRS = [
    ("EUR/GBP", "EURUSD_5m.parquet", "GBPUSD_5m.parquet", "close_EURUSD", "close_GBPUSD", 1.6, 1.0),
    ("Gold/Oil", "BCOUSD_5m.parquet", "XAUUSD_5m.parquet", "close_BCOUSD", "close_XAUUSD", 3.0, 3.0), 
    ("Oil/Silver", "BCOUSD_5m.parquet", "XAGUSD_5m.parquet", "close_BCOUSD", "close_XAGUSD", 3.0, 3.0),
    ("AUD/NZD", "NZDUSD_5m.parquet", "AUDUSD_5m.parquet", "close_NZDUSD", "close_AUDUSD", 2.0, 2.0),
    ("CAC/NZD", "NZDUSD_5m.parquet", "FRXEUR_5m.parquet", "close_NZDUSD", "close_FRXEUR", 3.0, 3.0),
    ("Gold/Silver", "XAUUSD_5m.parquet", "XAGUSD_5m.parquet", "close_XAUUSD", "close_XAGUSD", 3.0, 3.0),
    ("SPX/DAX", "SPXUSD_5m.parquet", "GRXEUR_5m.parquet", "close_SPXUSD", "close_GRXEUR", 3.0, 2.0),
    ("SPX/CAC", "SPXUSD_5m.parquet", "FRXEUR_5m.parquet", "close_SPXUSD", "close_FRXEUR", 3.0, 2.0),
    ("SPX/FTSE", "SPXUSD_5m.parquet", "UKXGBP_5m.parquet", "close_SPXUSD", "close_UKXGBP", 3.0, 2.0),
    ("SPX/Nikkei", "SPXUSD_5m.parquet", "JPXJPY_5m.parquet", "close_SPXUSD", "close_JPXJPY", 3.0, 2.0),
    ("SPX/HK", "SPXUSD_5m.parquet", "HKXHKD_5m.parquet", "close_SPXUSD", "close_HKXHKD", 4.0, 2.0),
    ("SPX/Dow", "SPXUSD_5m.parquet", "UDXUSD_5m.parquet", "close_SPXUSD", "close_UDXUSD", 2.0, 2.0),
    ("SPX/Nas", "SPXUSD_5m.parquet", "NSXUSD_5m.parquet", "close_SPXUSD", "close_NSXUSD", 2.0, 2.0),
    ("AUD/CAD", "AUDUSD_5m.parquet", "USDCAD_5m.parquet", "close_AUDUSD", "close_USDCAD", 2.0, 2.0),
    ("EUR/CHF", "EURUSD_5m.parquet", "USDCHF_5m.parquet", "close_EURUSD", "close_USDCHF", 2.0, 2.0),
    ("EUR/JPY", "EURUSD_5m.parquet", "USDJPY_5m.parquet", "close_EURUSD", "close_USDJPY", 2.0, 1.0),
    ("GBP/JPY", "GBPUSD_5m.parquet", "USDJPY_5m.parquet", "close_GBPUSD", "close_USDJPY", 2.0, 1.0),
    ("CHF/JPY", "USDCHF_5m.parquet", "USDJPY_5m.parquet", "close_USDCHF", "close_USDJPY", 2.0, 1.0),
    ("EUR/AUD", "EURUSD_5m.parquet", "AUDUSD_5m.parquet", "close_EURUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/AUD", "GBPUSD_5m.parquet", "AUDUSD_5m.parquet", "close_GBPUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/CAD", "GBPUSD_5m.parquet", "USDCAD_5m.parquet", "close_GBPUSD", "close_USDCAD", 2.0, 2.0),
    ("NZD/CAD", "NZDUSD_5m.parquet", "USDCAD_5m.parquet", "close_NZDUSD", "close_USDCAD", 2.0, 2.0),
]
PAIRS = PAIRS[:10]  # LIMIT TO TOP 10 FOR SPEED ASSESSMENT

def load_pair_data(fx, fy, cx, cy):
    try:
        p_x = os.path.join(DATA_DIR, fx)
        p_y = os.path.join(DATA_DIR, fy)
        if not os.path.exists(p_x) or not os.path.exists(p_y):
            # print(f"Missing {p_x} or {p_y}")
            return None
        df_x = pl.read_parquet(p_x).rename({cx: "X"})
        df_y = pl.read_parquet(p_y).rename({cy: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        
        # Filter 2018-2025
        # 5m timestamps might be high frequency, ensure range
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {fx}/{fy}: {e}")
        return None

def compute_kalman_states(y, x):
    # This loop is sequential and hard to vectorize without Numba.
    # We accept the cost but optimize internals.
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = np.zeros(len(y))
    errors = np.zeros(len(y))
    
    # Pre-compute means for stability
    # Rolling mean for centering
    s_x = pd.Series(x)
    s_y = pd.Series(y)
    mu_x = s_x.rolling(500, min_periods=1).mean().values
    mu_y = s_y.rolling(500, min_periods=1).mean().values
    
    # Kalman Loop
    for i in range(len(y)):
        # Centering (use pre-computed rolling means)
        # Note: Optimization: Only update KF.
        mx = mu_x[i]
        my = mu_y[i]
        
        b, resid = kf.update(x[i] - mx, y[i] - my)
        betas[i] = b
        errors[i] = (y[i] - my) - b * (x[i] - mx)
        
    return betas, errors

def compute_z_scores_vectorized(errors, window=500):
    s = pd.Series(errors)
    roll = s.rolling(window)
    # Shift 1 to avoid lookahead (using past 500 stats for current Z)
    mus = roll.mean().shift(1).fillna(0.0).values
    stds = roll.std().shift(1).fillna(1.0).values
    
    # Avoid div/0
    mask = stds > 1e-8
    z_scores = np.zeros_like(errors)
    z_scores[mask] = (errors[mask] - mus[mask]) / stds[mask]
    
    return z_scores

def compute_features_at_entry(i, y, x, betas, errors, z_scores, ts):
    # Feature extraction with checks
    features = {}
    
    try:
        # Signal Quality
        features['z_entry'] = round(z_scores[i], 2)
        prev_i = max(500, i - 5)
        features['z_velocity'] = round(z_scores[i] - z_scores[prev_i], 2)
        
        slice_start = max(0, i-500)
        features['spread_std'] = round(np.std(errors[slice_start:i]) * 10000, 2)
        
        beta_slice = max(0, i-100)
        features['beta_stability'] = round(np.std(betas[beta_slice:i]), 4)
        
        # Market Regime
        features['beta'] = round(betas[i], 4)
        
        # Vol checks
        y_slice = y[slice_start:i]
        x_slice = x[slice_start:i]
        
        if len(y_slice) > 1:
            vol_y = np.std(np.diff(y_slice))
            vol_x = np.std(np.diff(x_slice))
            features['vol_ratio'] = round(vol_y / vol_x if vol_x > 1e-9 else 1.0, 3)
        else:
            features['vol_ratio'] = 1.0
            
        if i >= 500:
            corr = np.corrcoef(x_slice, y_slice)[0, 1]
            features['correlation_500'] = round(corr, 3) if not np.isnan(corr) else 0.0
        else:
            features['correlation_500'] = 0.0
        
        # Trend
        if i >= 100:
            s_spread = y[i-100:i] - betas[i] * x[i-100:i]
            if len(s_spread) > 1:
                slope = np.polyfit(np.arange(len(s_spread)), s_spread, 1)[0]
                std_spread = np.std(s_spread)
                features['trend_strength'] = round(slope / (std_spread + 1e-8), 3)
            else:
                features['trend_strength'] = 0.0
        else:
            features['trend_strength'] = 0.0
        
        # Time
        item = ts[i]
        # Handle nanoseconds int or datetime
        if isinstance(item, (int, float, np.int64)):
            dt = pd.to_datetime(item, unit='ns') if item > 1e16 else pd.to_datetime(item, unit='s')
            features['hour'] = dt.hour
            features['day_of_week'] = dt.dayofweek
        else:
            features['hour'] = item.hour
            features['day_of_week'] = item.weekday()
            
        # Returns
        lookback = min(i, 16) # 16 bars * 5m = 80m? Or 4h? 
        # In H1 model, 4h = 4 bars.
        # In 5m model, 4h = 48 bars.
        # We should scale lookback? 
        # H1 model used lookback=4.
        # If we keep lookback 16 (from M15 code?)
        # Let's align with timeframe: "ret_4h" implies 4 hours.
        # 4 hours = 48 * 5m bars.
        lookback_4h = min(i, 48)
        features['ret_X_4h'] = round((x[i] - x[i - lookback_4h]) * 10000, 2)
        features['ret_Y_4h'] = round((y[i] - y[i - lookback_4h]) * 10000, 2)
        
        # Entry ATR (50 bars = 250m = 4h)
        if i >= 50:
            recent_ret = np.diff(y[i-50:i])
            features['entry_atr'] = round(np.std(recent_ret) * 10000, 2)
        else:
            features['entry_atr'] = 0.0
            
        # Vol Regime (Short vs Long)
        if i >= 500:
            short_vol = np.std(np.diff(y[i-50:i]))
            long_vol = np.std(np.diff(y[i-500:i]))
            features['vol_regime'] = round(short_vol / (long_vol + 1e-9), 2)
        else:
            features['vol_regime'] = 1.0
            
        features['atr_ratio'] = 1.0 # Simplified for speed
        
    except Exception as e:
        # print(f"Feature Error at {i}: {e}")
        return None
        
    return features

def simulate_trade(idx, direction, strategy, y, x, z, active, thresh, stop):
    # Same logic but simpler
    prices = y if active == 'Y' else x
    entry = prices[idx]
    
    # 5m Bar Duration Limit: 500 bars (41 hours)
    limit = min(idx + 500, len(z))
    
    for i in range(idx + 1, limit):
        curr = prices[i]
        curr_z = z[i]
        
        # Check Exits
        hit_stop = False
        hit_target = False
        
        if strategy == 'MOM':
            # Target: Z reverts to 0 (crosses 0) NO -> Z continues?
            # MOM Logic: 
            # Long (Z > 1.5): Exit if Z < 0 (Reversion occurred = Loss) OR Z > Stop (Momentum continues = Win)
            # Wait, MOM bets on Z expanding?
            # If Z > 1.5, we go Long.
            # If Z goes to 3.5, we Win?
            # If Z goes to 0, we Lose?
            if direction == 1: # Long
                if curr_z < 0: return (curr - entry)*10000, i-idx, 'LOSS_REV'
                if curr_z > stop: return (curr - entry)*10000, i-idx, 'WIN_MOM'
            else: # Short
                if curr_z > 0: return -(curr - entry)*10000, i-idx, 'LOSS_REV'
                if curr_z < -stop: return -(curr - entry)*10000, i-idx, 'WIN_MOM'
                
        else: # REV
            if direction == 1: # Long (Z < -1.5)
                # Exit if Z > 0 (Mean Reverted = Win)
                if curr_z > 0: return (curr - entry)*10000, i-idx, 'WIN_REV'
                if curr_z < -stop: return (curr - entry)*10000, i-idx, 'LOSS_MOM'
            else: # Short (Z > 1.5)
                if curr_z < 0: return -(curr - entry)*10000, i-idx, 'WIN_REV'
                if curr_z > stop: return -(curr - entry)*10000, i-idx, 'LOSS_MOM'
                
    # Timeout
    final_pnl = (prices[limit-1] - entry) * 10000 * direction
    return final_pnl, 500, 'TIMEOUT'

def build_dataset_optimized():
    print("--- 5M OPTIMIZED BUILDER ---")
    all_events = []
    
    for name, fx, fy, cx, cy, cy_cost, cx_cost in tqdm(PAIRS):
        df = load_pair_data(fx, fy, cx, cy)
        if df is None: continue
        
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        betas, errors = compute_kalman_states(y, x)
        z_scores = compute_z_scores_vectorized(errors)
        
        # Iterate signals
        # Only check indices where |Z| > 1.5 and |Z| < 5.0 (outlier filter)
        thresh = 1.5
        stop = 3.5
        
        # Optimization: Indices
        candidates = np.where((np.abs(z_scores) > thresh) & (np.abs(z_scores) < 6.0))[0]
        # Filter boundaries
        candidates = candidates[(candidates > 500) & (candidates < len(y) - 500)]
        
        # Debounce: Skip clustered signals to avoid 1000 events in 1 hour
        # Simple step: only take 1 signal every 12 bars (1 hour)?
        # Original code used `min_gap = 20`.
        
        last_mom = -100
        last_rev = -100
        min_gap = 20 
        
        # Candidates are sorted.
        for i in candidates:
            z = z_scores[i]
            beta = betas[i]
            
            # Whip/Tank
            if 0.98 <= beta <= 1.02: continue
            
            active = 'Y' if beta < 0.98 else 'X'
            
            # Feature extraction
            # Done only for valid signals
            feat = compute_features_at_entry(i, y, x, betas, errors, z_scores, ts)
            if feat is None: continue
            
            # MOM
            if i - last_mom >= min_gap:
                dr = 1 if z > 0 else -1
                pnl, dur, out = simulate_trade(i, dr, 'MOM', y, x, z_scores, active, thresh, stop)
                row = {
                    'pair': name, 'timestamp': str(ts[i]), 'year': int(str(ts[i])[:4]),
                    'strategy_type': 'MOM', 'active_leg': active, 'side': 'LONG' if dr==1 else 'SHORT',
                    'outcome': out, 'pnl_bps': pnl, 'duration_bars': dur,
                    **feat
                }
                all_events.append(row)
                last_mom = i
                
            # REV
            if i - last_rev >= min_gap:
                # Rev direction is opposite to Z
                # If Z > 0, we Short (dr = -1).
                # If Z < 0, we Long (dr = 1).
                dr = -1 if z > 0 else 1
                pnl, dur, out = simulate_trade(i, dr, 'REV', y, x, z_scores, active, thresh, stop)
                row = {
                    'pair': name, 'timestamp': str(ts[i]), 'year': int(str(ts[i])[:4]),
                    'strategy_type': 'REV', 'active_leg': active, 'side': 'LONG' if dr==1 else 'SHORT',
                    'outcome': out, 'pnl_bps': pnl, 'duration_bars': dur,
                    **feat
                }
                all_events.append(row)
                last_rev = i
        
    print(f"Total Events: {len(all_events)}")
    if all_events:
        pl.DataFrame(all_events).write_csv("data/meta_model/events_m5_8yr_v3_dual.csv")
        print("Saved.")

if __name__ == "__main__":
    build_dataset_optimized()
