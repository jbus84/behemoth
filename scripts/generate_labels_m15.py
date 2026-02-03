
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def generate_labels():
    print("--- META MODEL LABELLING SCAN (VOLUME CHECK) ---")
    
    # Load Data (2024 + 2025 for max data)
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    # Filter for 2 years
    df = df.filter(pl.col("timestamp").dt.year().is_in([2024, 2025]))
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    
    print("Calculating Kalman States...")
    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)
        errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
        
    COST_BPS_GBP = 1.6
    COST_BPS_EUR = 1.0
    
    print("| Threshold | Events (2 Years) | Avg PnL (bps) | Win Rate |")
    print("|---|---|---|---|")
    
    for thresh in [1.0, 1.25, 1.5, 2.0]:
        events = 0
        total_pnl = 0.0
        wins = 0
        
        in_pos = 0 # 1=Long, -1=Short
        active_asset = None
        entry_price = 0.0
        stop_level = max(3.5, thresh + 1.0)
        
        # We simulate the "Whip & Tank" Strategy logic
        # But we record EVERY signal > thresh as a label Candidate
        
        for i in range(500, len(y)):
            beta = betas[i]
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            
            # Regime
            if beta < 0.98: target_asset = 'GBP' 
            elif beta > 1.02: target_asset = 'EUR'
            else: target_asset = 'NEUTRAL'
            
            if in_pos == 0:
                if abs(z) > thresh:
                    # Valid Candidate Event
                    if target_asset == 'GBP':
                        if z > thresh: in_pos = 1; active_asset = 'GBP'; entry_price = y[i]
                        elif z < -thresh: in_pos = -1; active_asset = 'GBP'; entry_price = y[i]
                    elif target_asset == 'EUR':
                        if z > thresh: in_pos = -1; active_asset = 'EUR'; entry_price = x[i]
                        elif z < -thresh: in_pos = 1; active_asset = 'EUR'; entry_price = x[i]
            
            elif in_pos != 0:
                # Exit Logic
                closed = False
                pnl = 0.0
                curr_gbp, curr_eur = y[i], x[i]
                
                if active_asset == 'GBP': # Momentum Exit
                    if in_pos == 1:
                        if z < 0: pnl = (curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                        elif z > stop_level: pnl = (curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                    elif in_pos == -1:
                        if z > 0: pnl = -(curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                        elif z < -stop_level: pnl = -(curr_gbp - entry_price)*10000 - COST_BPS_GBP; closed = True
                elif active_asset == 'EUR': # Momentum Exit
                    if in_pos == -1:
                        if z < 0: pnl = -(curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                        elif z > stop_level: pnl = -(curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                    elif in_pos == 1:
                        if z > 0: pnl = (curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                        elif z < -stop_level: pnl = (curr_eur - entry_price)*10000 - COST_BPS_EUR; closed = True
                
                if closed:
                    events += 1
                    total_pnl += pnl
                    if pnl > 0: wins += 1
                    in_pos = 0; active_asset = None
                    
        avg_pnl = total_pnl / events if events > 0 else 0
        wr = wins / events * 100 if events > 0 else 0
        print(f"| {thresh} | {events} | {avg_pnl:.2f} | {wr:.1f}% |")

if __name__ == "__main__":
    generate_labels()
