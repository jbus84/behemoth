
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def optimize_m15_threshold():
    print("--- M15 THRESHOLD OPTIMIZATION (FRX/BCO) ---")
    
    p_y = os.path.join(DATA_DIR, "FRXEUR_15m.parquet")
    p_x = os.path.join(DATA_DIR, "BCOUSD_15m.parquet")
    
    if not os.path.exists(p_y) or not os.path.exists(p_x):
        print("M15 Data Not Found.")
        return

    df_y = pl.read_parquet(p_y).rename({"close_FRXEUR": "Y"})
    df_x = pl.read_parquet(p_x).rename({"close_BCOUSD": "X"})
    
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
    
    cost_bps = 9.0 # Spread cost (higher relative impact on M15)

    def run_year(year):
        print(f"\n--- YEAR {year} ---")
        start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(year, 12, 31, tzinfo=timezone.utc)
        sub = df.filter((pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt))
        
        y = np.log(sub["Y"].to_numpy())
        x = np.log(sub["X"].to_numpy())
        
        # Kalman
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []
        y_win, x_win = [], []
        
        for i in range(len(y)):
            y_win.append(y[i]); x_win.append(x[i])
            if len(y_win)>500: y_win.pop(0); x_win.pop(0)
            if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
            b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
            betas.append(b)
            errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
            
        thresholds = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
        
        print("| Threshold | Net PnL (bps) | Trades | Win Rate |")
        print("|---|---|---|---|")
        
        for thresh in thresholds:
            in_pos = 0
            pnl_total = 0.0
            trades = 0
            wins = 0
            entry_y, entry_x, entry_beta = 0., 0., 0.
            
            stop_level = max(3.5, thresh + 1.0)
            
            for i in range(500, len(y)):
                window = errors[i-500:i]
                mu, std = np.mean(window), np.std(window)
                if std < 1e-6: continue
                z = (errors[i] - mu) / std
                
                pnl = 0.0
                
                if in_pos == 0:
                    if z > thresh: in_pos = -1; entry_beta=betas[i-1]; entry_y=y[i]; entry_x=x[i]
                    elif z < -thresh: in_pos = 1; entry_beta=betas[i-1]; entry_y=y[i]; entry_x=x[i]
                elif in_pos == 1:
                    if z > 0.0: # Win
                        gross = (y[i]-entry_y) - entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades+=1; wins+=1
                    elif z < -stop_level: # Stop
                        gross = (y[i]-entry_y) - entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades+=1
                elif in_pos == -1:
                    if z < 0.0: # Win
                        gross = -(y[i]-entry_y) + entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades+=1; wins+=1
                    elif z > stop_level: # Stop
                        gross = -(y[i]-entry_y) + entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades+=1
                
                pnl_total += pnl
                
            wr = wins/trades*100 if trades > 0 else 0
            print(f"| {thresh} | {pnl_total:.1f} | {trades} | {wr:.1f}% |")

    run_year(2022)
    run_year(2025)

if __name__ == "__main__":
    optimize_m15_threshold()
