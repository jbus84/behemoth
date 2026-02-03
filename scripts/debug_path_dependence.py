
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"

def debug_memory():
    print("--- FILTER MEMORY DIAGNOSTIC (FRX/BCO) ---")
    
    p_y = os.path.join(DATA_DIR, "FRXEUR_1h.parquet")
    p_x = os.path.join(DATA_DIR, "BCOUSD_1h.parquet")
    
    df_y = pl.read_parquet(p_y).rename({"close_FRXEUR": "Y"})
    df_x = pl.read_parquet(p_x).rename({"close_BCOUSD": "X"})
    
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
    
    # 1. Fresh Run (2025 Only)
    print("\n[TEST 1] Fresh Start (Jan 1, 2025)")
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    sub = df.filter(pl.col("timestamp") >= start_dt)
    y = np.log(sub["Y"].to_numpy())
    x = np.log(sub["X"].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    
    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)
        
    print(f"Final Beta (Fresh): {betas[-1]:.4f}")
    
    # 2. Stale Run (2023-2025)
    print("\n[TEST 2] Stale Start (Jan 1, 2023 -> 2025)")
    start_dt_long = datetime(2023, 1, 1, tzinfo=timezone.utc)
    sub_long = df.filter(pl.col("timestamp") >= start_dt_long)
    y_long = np.log(sub_long["Y"].to_numpy())
    x_long = np.log(sub_long["X"].to_numpy())
    ts_long = sub_long["timestamp"].to_numpy()
    
    kf2 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas_long = []
    
    # Find index where 2025 starts
    idx_2025 = -1
    for i, t in enumerate(ts_long):
        if t >= np.datetime64('2025-01-01'):
            if idx_2025 == -1: idx_2025 = i
            
    for i in range(len(y_long)):
        if i < 10: mu_y, mu_x = y_long[i], x_long[i]
        else: mu_y, mu_x = np.mean(y_long[max(0,i-500):i]), np.mean(x_long[max(0,i-500):i])
        b, _ = kf2.update(x_long[i]-mu_x, y_long[i]-mu_y)
        betas_long.append(b)
        
    print(f"Final Beta (Stale): {betas_long[-1]:.4f}")
    print(f"Beta Difference: {abs(betas[-1] - betas_long[-1]):.4f}")
    
    if abs(betas[-1] - betas_long[-1]) > 0.1:
        print("Verdict: SIGNIFICANT MEMORY DRIFT detected.")
    else:
        print("Verdict: No Drift.")

if __name__ == "__main__":
    debug_memory()
