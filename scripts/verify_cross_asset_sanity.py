
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"
Y_SYM = "FRXEUR" # CAC 40
X_SYM = "AUDCAD" # AUD/CAD
COST_BPS = 2.0

def verify_sanity():
    print(f"--- CROSS-ASSET SANITY CHECK: {Y_SYM} vs {X_SYM} ---")
    
    # Load
    df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_4h.parquet"))
    df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_4h.parquet"))

    # 2025 Filter
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2025, 12, 31, tzinfo=timezone.utc)
    
    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).filter(
        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
    ).sort("timestamp")
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    print(f"Data Points: {len(y)}")
    
    # Volatility Check
    vol_y = np.std(np.diff(y)) * 10000
    vol_x = np.std(np.diff(x)) * 10000
    print(f"Volatility Y ({Y_SYM}): {vol_y:.2f} bps/bar")
    print(f"Volatility X ({X_SYM}): {vol_x:.2f} bps/bar")
    print(f"Vol Ratio (Y/X): {vol_y/vol_x:.2f}")
    
    # Kalman
    kf = KalmanFilterReg(Q=1e-9, R=1e-3)
    betas = []
    errors = []
    
    for i in range(len(y)):
        b, _ = kf.update(x[i], y[i])
        betas.append(b)
        errors.append(y[i] - b * x[i])
        
    avg_beta = np.mean(betas)
    print(f"Average Beta: {avg_beta:.4f}")
    
    if abs(avg_beta) > 2.0:
        print(f"WARNING: High Beta implies leverage! Holding {avg_beta:.2f}x notional in {X_SYM}.")
    
    # Trade Decomposition
    in_pos = 0
    entry_y, entry_x, entry_beta = 0, 0, 0
    
    pnl_y_total = 0
    pnl_x_total = 0
    trades = 0
    
    for i in range(50, len(y)):
        window = errors[i-50:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        beta = betas[i-1]
        
        if in_pos == 0:
            if z > 2.0: in_pos = -1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
            elif z < -2.0: in_pos = 1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
        elif in_pos == 1: # Long Spread (Long Y, Short Beta*X)
            if z > 0 or z < -3:
                # PnL Y = Y_out - Y_in
                # PnL X = -Beta * (X_out - X_in)
                py = (y[i] - entry_y) * 10000
                px = -entry_beta * (x[i] - entry_x) * 10000
                pnl_y_total += py
                pnl_x_total += px
                trades += 1; in_pos = 0
        elif in_pos == -1: # Short Spread (Short Y, Long Beta*X)
             if z < 0 or z > 3:
                py = -(y[i] - entry_y) * 10000
                px = entry_beta * (x[i] - entry_x) * 10000
                pnl_y_total += py
                pnl_x_total += px
                trades += 1; in_pos = 0
                
    total_net = pnl_y_total + pnl_x_total - (trades * COST_BPS)
    
    print("\n--- PnL DECOMPOSITION ---")
    print(f"Trades: {trades}")
    print(f"Total PnL from {Y_SYM} (Index): {pnl_y_total:.0f} bps")
    print(f"Total PnL from {X_SYM} (FX):    {pnl_x_total:.0f} bps")
    print(f"Net PnL (after {COST_BPS}bps cost): {total_net:.2f} bps")
    
    if abs(pnl_x_total) > abs(pnl_y_total) * 5:
        print("VERDICT: BUG/SKEWED. Alpha is pure leverage on the FX leg.")
    else:
        print("VERDICT: BALANCED. Both legs contribute, or beta adjusts volatility correctly.")

if __name__ == "__main__":
    verify_sanity()
