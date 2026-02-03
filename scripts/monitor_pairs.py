
import polars as pl
import numpy as np
import pandas as pd
import os
from kalman_filter import KalmanFilterReg

# === CONFIGURATION ===
# The "Golden Six" Verified Portfolio
PAIR_CONFIGS = [
    ("Gold / Silver", "pairs_metals_4h.parquet", "close_XAUUSD", "close_XAGUSD", 0.0003),
    ("AUD / NZD", "pairs_aud_nzd_4h.parquet", "close_AUDUSD", "close_NZDUSD", 0.0003),
    ("Brent / CAD", "pairs_oil_cad_4h.parquet", "close_BCOUSD", "close_USDCAD", 0.0003),
    ("Nasdaq / SPX", "pairs_indices_4h.parquet", "close_NSXUSD", "close_SPXUSD", 0.0003),
    ("EUR / GBP", "pairs_fx_4h.parquet", "close_EURUSD", "close_GBPUSD", 0.0002),
    ("DAX / FTSE", "pairs_dax_ftse_4h.parquet", "close_GRXEUR", "close_UKXGBP", 0.0003),
]

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/pairs"

def monitor_pair(name, file, col_y, col_x, cost_bps):
    path = f"{DATA_DIR}/{file}"
    if not os.path.exists(path):
        return None

    try:
        df = pl.read_parquet(path).sort("timestamp")
    except:
        return None
    
    # 1. Kalman Filter (Online Training)
    y_raw = np.log(df[col_y].to_numpy())
    x_raw = np.log(df[col_x].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    
    # We only need the *current* state really, but let's run history
    # to build the Z-Score distribution.
    spreads = []
    betas = []
    
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        spreads.append(spread)
        betas.append(beta)
        
    # 2. Metric Calculation
    s_series = pd.Series(spreads)
    
    # Z-Score (30-Period Rolling)
    roll_mean = s_series.rolling(30).mean()
    roll_std = s_series.rolling(30).std()
    z_score = (s_series - roll_mean) / roll_std
    
    current_z = z_score.iloc[-1]
    current_beta = betas[-1]
    current_spread = spreads[-1]
    
    # 3. Decision Logic (No Stops, Z=0 Exit)
    # This is for display only - the execution logic is in the Guide.
    
    status = "WAIT"
    action = "HOLD"
    
    if current_z > 2.0:
        status = "OVER-EXTENDED"
        action = "SELL SPREAD (Short Y / Long X)"
    elif current_z < -2.0:
        status = "OVER-COMPRESSED"
        action = "BUY SPREAD (Long Y / Short X)"
    elif abs(current_z) < 0.1:
        status = "FAIR VALUE"
        action = "EXIT ALL"
        
    return {
        "Pair": name,
        "Z-Score": current_z,
        "Beta": current_beta,
        "Status": status,
        "Action": action
    }

def run_dashboard():
    print(f"{'PAIR':<15} | {'Z-SCORE':<8} | {'BETA':<8} | {'STATUS':<15} | {'ACTION'}")
    print("-" * 75)
    
    for name, file, y, x, cost in PAIR_CONFIGS:
        res = monitor_pair(name, file, y, x, cost)
        if res:
            z_str = f"{res['Z-Score']:.2f}"
            b_str = f"{res['Beta']:.3f}"
            print(f"{res['Pair']:<15} | {z_str:<8} | {b_str:<8} | {res['Status']:<15} | {res['Action']}")
        else:
            print(f"{name:<15} | N/A      | N/A      | NO DATA         | CHECK FEED")

if __name__ == "__main__":
    print("=== KALMAN PAIRS DASHBOARD (4H) ===\n")
    run_dashboard()
    print("\n[NOTE] Check 'kalman_strategy_guide.md' for execution rules.")
