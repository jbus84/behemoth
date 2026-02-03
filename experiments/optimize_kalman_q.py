
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def optimize_kalman_q():
    print("--- KALMAN SENSITIVITY OPTIMIZATION (Q FACTOR) ---")
    print("Testing impact of Q (Adaptivity) on Trade Frequency and PnL.")
    
    # Load Data (2025)
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == 2025)
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    thresh = 2.0
    stop_level = 3.5
    COST_BPS_GBP = 1.6
    COST_BPS_EUR = 1.0
    
    print("| Q Param | Net PnL (bps) | Trades | Adaptivity |")
    print("|---|---|---|---|")
    
    # Testing Q range
    # 1e-4 = Very Loose (Fast). 1e-8 = Very Stiff (Slow).
    for Q in [1e-4, 1e-5, 1e-6, 1e-7, 1e-8]:
        
        kf = KalmanFilterReg(Q=Q, R=1e-3)
        betas = []
        errors = []
        
        for i in range(len(y)):
            if i < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
            b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
            betas.append(b)
            errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
            
        total_pnl = 0.0
        trades = 0
        in_pos = 0; active_asset = None; entry_price = 0.0
        
        # Dynamic Strategy Loop
        for i in range(500, len(y)):
            beta_val = betas[i]
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            
            # Regime Selection
            if beta_val < 0.98: target_asset = 'GBP' # Tank = GBP -> Momentum
            elif beta_val > 1.02: target_asset = 'EUR' # Tank = EUR -> Momentum
            else: target_asset = 'NEUTRAL'
            
            curr_gbp = y[i]
            curr_eur = x[i]
            
            # Entry
            if in_pos == 0:
                if target_asset == 'GBP':
                    if z > thresh: in_pos = 1; active_asset = 'GBP'; entry_price = curr_gbp
                    elif z < -thresh: in_pos = -1; active_asset = 'GBP'; entry_price = curr_gbp
                elif target_asset == 'EUR':
                    if z > thresh: in_pos = -1; active_asset = 'EUR'; entry_price = curr_eur
                    elif z < -thresh: in_pos = 1; active_asset = 'EUR'; entry_price = curr_eur
            
            # Exit
            elif in_pos != 0:
                closed = False
                pnl = 0.0
                
                # Momentum Exit Logic (Inverse Reversion)
                if active_asset == 'GBP':
                    if in_pos == 1: # Long
                        if z < 0: pnl = (curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                        elif z > stop_level: pnl = (curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                    elif in_pos == -1: # Short
                        if z > 0: pnl = -(curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                        elif z < -stop_level: pnl = -(curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True

                elif active_asset == 'EUR':
                    if in_pos == -1: # Short
                        if z < 0: pnl = -(curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                        elif z > stop_level: pnl = -(curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                    elif in_pos == 1: # Long
                        if z > 0: pnl = (curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                        elif z < -stop_level: pnl = (curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                
                if closed:
                    total_pnl += pnl
                    trades += 1
                    in_pos = 0; active_asset = None
        
        adaptivity = "Very Fast" if Q >= 1e-4 else "Fast" if Q >= 1e-5 else "Moderate" if Q >= 1e-6 else "Slow" if Q >= 1e-7 else "Very Slow"
        print(f"| {Q} | {total_pnl:.1f} | {trades} | {adaptivity} |")

if __name__ == "__main__":
    optimize_kalman_q()
