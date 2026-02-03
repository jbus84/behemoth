print("DEBUG: Script Loaded", flush=True)
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

# Batch Audit Configuration
PAIRS = [
    ("FRXEUR", "AUDCAD", "4h", 2.0, "CAC40/AUDCAD (Clipped)"),
    ("SPXUSD", "NZDCAD", "4h", 2.0, "S&P/NZDCAD (Clipped)"),
    ("GRXEUR", "NZDCAD", "4h", 2.0, "DAX/NZDCAD (Clipped)"),
    ("AUDUSD", "USDCAD", "4h", 2.0, "AUD/CAD (Control)"),
    ("GRXEUR", "UKXGBP", "4h", 5.0, "DAX/FTSE (Control)"),
]

DIRS = { "1h": "data/global_1h", "4h": "data/global_4h" }

def audit_real_pnl():
    print("DEBUG: Starting Audit Script...")
    print(f"--- GLOBAL REAL PnL AUDIT (Beta Clipped [-3, 3]) ---")
    print("| Pair | TF | Real PnL (bps) | Trades | Verdict |")
    print("|---|---|---|---|---|")
    
    for y_sym, x_sym, tf, cost, label in PAIRS:
        run_single_pair(y_sym, x_sym, tf, cost, label)

def run_single_pair(y_sym, x_sym, tf, cost, label):
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
    ).sort("timestamp")
    
    if len(df) < 500: return
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    # STUBBORN FILTER (Q=1e-9)
    kf = KalmanFilterReg(Q=1e-9, R=1e-3)
    
    betas, errors = [], []
    for i in range(len(y)):
        b, _ = kf.update(x[i], y[i])
        betas.append(b)
        errors.append(y[i] - b * x[i])
        
    real_pnls = []
    in_pos = 0 
    entry_beta, entry_y, entry_x = 0., 0., 0.
    
    trades = 0
    
    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        # KEY FIX: Clip Beta to avoid implicit leverage
        raw_beta = betas[i-1]
        beta = np.clip(raw_beta, -3.0, 3.0) 
        
        if in_pos == 0:
            if z > 2.0:
                in_pos = -1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
            elif z < -2.0:
                in_pos = 1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
        elif in_pos == 1:
            if z > 0.0 or z < -3.0:
                pnl_y = y[i] - entry_y
                pnl_x = entry_beta * (x[i] - entry_x)
                real_pnl = (pnl_y - pnl_x) * 10000 - cost
                real_pnls.append(real_pnl)
                in_pos = 0; trades += 1
        elif in_pos == -1:
            if z < 0.0 or z > 3.0:
                pnl_y = -(y[i] - entry_y) + entry_beta*(x[i] - entry_x)
                real_pnl = (pnl_y + pnl_x) * 10000 - cost
                real_pnls.append(real_pnl)
                in_pos = 0; trades += 1

    if len(real_pnls) > 0:
        avg = np.mean(real_pnls)
        print(f"| {label} | {tf} | **{avg:.2f}** | {trades} | {'PASS' if avg > 0 else 'FAIL'} |")

if __name__ == '__main__':
    audit_real_pnl()
