
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil"),
]

def audit_h1_full():
    print("--- H1 FULL HISTORY AUDIT (2018-2025) [Multi-Threshold] ---")
    
    for y_sym, x_sym, label in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_1h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_1h.parquet")
        
        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})
        
        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
        
        y_log = np.log(df["Y"].to_numpy())
        x_log = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        
        # Kalman
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []
        y_win, x_win = [], []
        
        for i in range(len(y_log)):
            y_win.append(y_log[i]); x_win.append(x_log[i])
            if len(y_win)>500: y_win.pop(0); x_win.pop(0)
            if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
            else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
            b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
            betas.append(b)
            errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))
            
        THRESHOLDS = [2.0, 2.5, 3.0, 3.5]
        years = range(2018, 2026)
        
        print(f"\n{label} Analysis:")
        # Header
        header = "| Threshold | " + " | ".join(map(str, years)) + " | **Total** |"
        print(header)
        print("|" + "---|" * (len(years) + 2))
        
        for THRESH in THRESHOLDS:
            results = {}
            in_pos = 0
            entry_beta, entry_y, entry_x = 0., 0., 0.
            cost_bps = 9.0
            
            # Stop logic: Max(3.5, Thresh+1.0)
            STOP = max(3.5, THRESH + 1.0)
            
            for i in range(500, len(y_log)):
                dt = ts[i]
                yr = dt.astype('datetime64[Y]').astype(int) + 1970
                
                window = errors[i-500:i]
                mu, std = np.mean(window), np.std(window)
                if std < 1e-6: continue
                z = (errors[i] - mu) / std
                
                pnl = 0.0
                
                if in_pos == 0:
                    if z > THRESH: in_pos = -1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
                    elif z < -THRESH: in_pos = 1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
                elif in_pos == 1:
                    if z > 0.0: # Win
                        gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
                    elif z < -STOP: # Stop
                        gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
                elif in_pos == -1:
                    if z < 0.0: # Win
                        gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
                    elif z > STOP: # Stop
                        gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0
                        
                if yr not in results: results[yr] = []
                if pnl != 0.0: results[yr].append(pnl)
                
            # Row Output
            row_str = f"| {THRESH} | "
            total = 0
            for yr in years:
                yr_pnl = sum(results.get(yr, []))
                total += yr_pnl
                row_str += f"{yr_pnl:.0f} | "
            row_str += f"**{total:.0f}** |"
            print(row_str)

if __name__ == "__main__":
    audit_h1_full()
