
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

# Configuration
PAIRS = [
    # Tier 1
    ("EU50EUR", "FRXEUR", "1h", "EU50/FRA40"),
    ("BCOUSD", "GRXEUR", "1h", "Oil/DAX"),
    ("AUDUSD", "NZDUSD", "1h", "AUD/NZD"), # Assuming components for AUD/NZD or direct? 
    # Wait, AUD/NZD might be a direct pair or constructed.
    # The user manual says "AUD/NZD (Spot FX)". 
    # Let's check file existence first. 
    # If not found, I will skip or try AUDUSD/NZDUSD.
    ("BCOUSD", "UKXGBP", "4h", "Oil/FTSE"), 
    
    # Tier 2 / Diversifiers
    ("SPXUSD", "NSXUSD", "1h", "S&P/Nasdaq"),
    ("BCOUSD", "FRXEUR", "1h", "Oil/CAC"),
    
    # NEW DIVERSIFIERS
    ("ETXEUR", "UKXGBP", "1h", "Euro/FTSE"),
    ("ETXEUR", "GRXEUR", "1h", "Euro/DAX"),
    ("JPXJPY", "GRXEUR", "1h", "Nikkei/DAX"),
    ("SPXUSD", "GRXEUR", "1h", "S&P/DAX"),
    ("EURUSD", "GBPUSD", "4h", "Euro/Pound (H4)"),
]

# DIRECTORIES
DIRS = {
    "1h": "data/global_1h",
    "4h": "data/global_4h"
}

COSTS = {
    "BCOUSD": 9.0, # Oil based
    "EU50EUR": 4.0, # Liquid EU
    "SPXUSD": 3.0, # Liquid US
    "AUDUSD": 2.0, # FX
    "ETXEUR": 4.0, # Liquid EU
    "JPXJPY": 6.0, # Asia (Higher spread?)
    "EURUSD": 1.5, # Liquid FX
}
DEFAULT_COST = 5.0

def get_cost(y_sym):
    return COSTS.get(y_sym, DEFAULT_COST)

def run_audit():
    print(f"--- 2025 PERFORMANCE AUDIT (Tier 1 & 2) ---")
    print("| Pair | TF | Win Rate | Avg Win | Avg Loss | Expt Value | Net ROI | Trades |")
    print("|---|---|---|---|---|---|---|---|")
    
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2025, 12, 31, tzinfo=timezone.utc)
    
    for y_sym, x_sym, tf, label in PAIRS:
        data_dir = DIRS[tf]
        
        # 1. Load Data
        try:
            # Handle FX naming (AUDUSD vs AUDNZD)
            # If AUD/NZD is a single ticker:
            if label == "AUD/NZD" and not os.path.exists(os.path.join(data_dir, f"{y_sym}_{tf}.parquet")):
                 # Maybe it's AUDNZD directly?
                 if os.path.exists(os.path.join(data_dir, f"AUDNZD_{tf}.parquet")):
                     y_sym = "AUDNZD"
                     # Direct pair, X is dummy? No, Kalman needs 2 assets.
                     # If it's a direct cross, we trade it vs... nothing? Mean reverting on itself?
                     # The strategy is Pairs Trading.
                     # AUD/NZD implies trading AUD against NZD.
                     # Let's assume we use AUDUSD and NZDUSD.
                     pass 
            
            p_y = os.path.join(data_dir, f"{y_sym}_{tf}.parquet")
            p_x = os.path.join(data_dir, f"{x_sym}_{tf}.parquet")
            
            if not os.path.exists(p_y) or not os.path.exists(p_x):
                # Try adding .cash suffix or similar if needed, or skip
                # print(f"Skipping {label}: Files not found.")
                continue
                
            df_y = pl.read_parquet(p_y)
            df_x = pl.read_parquet(p_x)
            
        except Exception as e:
            # print(f"Error loading {label}: {e}")
            continue

        # 2. Align & Filter 2025
        df = df_y.rename({f"close_{y_sym}": "Y"}).join(
            df_x.rename({f"close_{x_sym}": "X"}), on="timestamp", how="inner"
        ).filter(
            (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
        ).sort("timestamp")
        
        if len(df) < 100:
            # print(f"Skipping {label}: Insufficient data for 2025 ({len(df)} rows).")
            continue
            
        # 3. Kalman Calc
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        y_vals = np.log(df["Y"].to_numpy())
        x_vals = np.log(df["X"].to_numpy())
        
        errors = []
        # Warmup on first few, but we only have 2025 data here.
        # Ideally we warm up on 2024.
        # For this script, we'll slice 2025 but accept potential warmup noise in Jan.
        # Or filters are fast.
        
        for i in range(len(y_vals)):
            b, _ = kf.update(x_vals[i], y_vals[i])
            errors.append(y_vals[i] - b * x_vals[i])
            
        # 4. Backtest
        trades_bps = []
        in_pos = 0
        entry_val = 0.0
        
        cost_bps = get_cost(y_sym) + 1.0 # Spread + 1bps Slippage
        
        # Window for Z-Score
        # If we start cold at Jan 1, we need window.
        # limit loop to starts > 200
        start_idx = 200 if len(y_vals) > 200 else 0
        
        for i in range(start_idx, len(y_vals)):
            window = errors[i-200:i]
            if len(window) < 20: continue
            
            mu = np.mean(window)
            std = np.std(window)
            if std < 1e-6: continue
            
            z = (errors[i] - mu) / std
            spread = errors[i]
            
            if in_pos == 0:
                if z > 2.0:
                    in_pos = -1
                    entry_val = spread
                elif z < -2.0:
                    in_pos = 1
                    entry_val = spread
            elif in_pos == 1:
                # Long Exit
                if z > 0.0 or z < -4.0:
                    pnl = spread - entry_val
                    trades_bps.append(pnl*10000 - cost_bps)
                    in_pos = 0
            elif in_pos == -1:
                # Short Exit
                if z < 0.0 or z > 4.0:
                    pnl = entry_val - spread
                    trades_bps.append(pnl*10000 - cost_bps)
                    in_pos = 0

        # 5. Stats
        trades_arr = np.array(trades_bps)
        if len(trades_arr) == 0:
            print(f"| **{label}** | {tf} | N/A | - | - | - | - | 0 |")
            continue
            
        win_rate = np.mean(trades_arr > 0) * 100
        avg_win = np.mean(trades_arr[trades_arr > 0]) if np.any(trades_arr > 0) else 0
        avg_loss = np.mean(trades_arr[trades_arr <= 0]) if np.any(trades_arr <= 0) else 0
        expt_val = np.mean(trades_arr)
        total_roi = np.sum(trades_arr) # Sum of BPS
        
        print(f"| **{label}** | {tf} | {win_rate:.1f}% | {avg_win:.0f} bps | {avg_loss:.0f} bps | **{expt_val:.0f} bps** | {total_roi:.0f} bps | {len(trades_arr)} |")

if __name__ == "__main__":
    run_audit()
