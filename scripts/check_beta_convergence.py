
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def check_convergence():
    print("--- CHECKING BETA CONVERGENCE SPEED ---")
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    # Use 2025 start to simulate "Turning it on"
    df = df.filter(pl.col("timestamp").dt.year() == 2025)
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    
    print("| Bar | Time (approx) | Beta | Stability (Change) |")
    print("|---|---|---|---|")
    
    prev_beta = 0
    
    for i in range(2000): # First 2000 bars
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        
        if i in [10, 50, 100, 200, 500, 1000, 1500]:
            change = abs(b - prev_beta)
            # Time classification
            if i == 10: t = "2.5 Hours"
            elif i == 100: t = "1 Day"
            elif i == 500: t = "1 Week"
            elif i == 1000: t = "2 Weeks"
            else: t = f"{i*15/60:.1f} Hours"
            
            print(f"| {i} | {t} | {b:.4f} | {change:.6f} |")
            
        prev_beta = b

if __name__ == "__main__":
    check_convergence()
