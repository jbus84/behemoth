
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

# Batch Audit Configuration
PAIRS = [
    ("FRXEUR", "BCOUSD", "4h", 9.0, "CAC/Oil (#1)"),
    ("USDCHF", "GRXEUR", "4h", 3.0, "CHF/DAX (#2)"),
    ("XAUUSD", "BCOUSD", "4h", 10.0, "Gold/Oil (#3)"),
    ("FRXEUR", "EURGBP", "4h", 2.5, "CAC/EURGBP (#4)"),
    ("UDXUSD", "GRXEUR", "4h", 5.0, "USD/DAX (#5)"),
]

DIRS = { "4h": "data/global_4h" }

def audit_real_pnl_2025():
    print(f"--- 2024 REAL PnL AUDIT (Centered, Threshold=1.5) ---")
    print("| Pair | TF | Gross PnL (bps) | Trades | Verdict |")
    print("|---|---|---|---|---|")
    
    start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2024, 12, 31, tzinfo=timezone.utc)
    
    for y_sym, x_sym, tf, cost, label in PAIRS:
        run_single_pair(y_sym, x_sym, tf, cost, label, start_dt, end_dt)

def run_single_pair(y_sym, x_sym, tf, cost, label, start_dt, end_dt):
    data_dir = DIRS[tf]
    try:
        p_y = os.path.join(data_dir, f"{y_sym}_{tf}.parquet")
        p_x = os.path.join(data_dir, f"{x_sym}_{tf}.parquet")
        if not os.path.exists(p_y) or not os.path.exists(p_x): return
        df_y = pl.read_parquet(p_y)
        df_x = pl.read_parquet(p_x)
    except: return

    df = df_y.rename({f"close_{y_sym}": "Y"}).join(
        df_x.rename({f"close_{x_sym}": "X"}), on="timestamp", how="inner"
    ).filter(
        (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
    ).sort("timestamp")
    
    if len(df) < 500: return
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    y_win, x_win = [], []
    
    for i in range(len(y)):
        y_win.append(y[i])
        x_win.append(x[i])
        if len(y_win) > 500: y_win.pop(0); x_win.pop(0)
        
        if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
            
        y_c = y[i] - mu_y
        x_c = x[i] - mu_x
        
        b, _ = kf.update(x_c, y_c)
        betas.append(b)
        errors.append(y_c - b * x_c)
        
    real_pnls = []
    in_pos = 0 
    entry_beta, entry_y, entry_x = 0., 0., 0.
    trades = 0
    
    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        beta = betas[i-1]
        
        # LOWER THRESHOLD TO 1.5
        if in_pos == 0:
            if z > 1.5: in_pos = -1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
            elif z < -1.5: in_pos = 1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
        elif in_pos == 1:
            if z > 0.0 or z < -2.0: # Exit at mean or stop loss (widened stop slightly) 
                pnl = ((y[i]-entry_y) - entry_beta*(x[i]-entry_x)) * 10000 - cost
                real_pnls.append(pnl); in_pos=0; trades+=1
        elif in_pos == -1:
            if z < 0.0 or z > 2.0:
                pnl = (-(y[i]-entry_y) + entry_beta*(x[i]-entry_x)) * 10000 - cost
                real_pnls.append(pnl); in_pos=0; trades+=1
                
    if len(real_pnls) > 0:
        avg = np.mean(real_pnls)
        print(f"| {label} | {tf} | **{avg:.2f}** | {trades} | {'PASS' if avg > 0 else 'FAIL'} |")

if __name__ == "__main__":
    audit_real_pnl_2025()
