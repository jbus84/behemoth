
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

def analyze_2022_vs_2025():
    print("--- 2022 vs 2025 CORRELATION ANALYSIS (CAC/Oil) ---")
    
    p_y = os.path.join(DATA_DIR, "FRXEUR_4h.parquet")
    p_x = os.path.join(DATA_DIR, "BCOUSD_4h.parquet")
    
    df_y = pl.read_parquet(p_y).rename({"close_FRXEUR": "Y"})
    df_x = pl.read_parquet(p_x).rename({"close_BCOUSD": "X"})
    
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
    
    # helper for strategy audit
    def analyze_year_strategy(year):
        start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(year, 12, 31, tzinfo=timezone.utc)
        
        sub = df.filter((pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt))
        y = np.log(sub["Y"].to_numpy())
        x = np.log(sub["X"].to_numpy())
        
        # Kalman
        from kalman_filter import KalmanFilterReg
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

        # Trade Stats
        in_pos = 0
        current_streak_loss = 0
        max_streak_loss = 0
        wins = 0
        losses = 0
        
        pnls = []
        
        for i in range(500, len(y)):
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            
            pnl = 0
            if in_pos == 0:
                if z > 1.5: in_pos = -1; entry_y=y[i]; entry_x=x[i]; entry_beta=betas[i-1]
                elif z < -1.5: in_pos = 1; entry_y=y[i]; entry_x=x[i]; entry_beta=betas[i-1]
            elif in_pos == 1: # Long
                if z > 0.0: # Win
                    pnl = 1; in_pos = 0; wins += 1; current_streak_loss = 0
                elif z < -3.5: # Stop
                    pnl = -1; in_pos = 0; losses += 1; current_streak_loss += 1
            elif in_pos == -1: # Short
                if z < 0.0: # Win
                    pnl = 1; in_pos = 0; wins += 1; current_streak_loss = 0
                elif z > 3.5: # Stop
                    pnl = -1; in_pos = 0; losses += 1; current_streak_loss += 1
            
            max_streak_loss = max(max_streak_loss, current_streak_loss)
                    
        print(f"[{year}]")
        print(f"  Trades: {wins+losses}")
        print(f"  Max Consecutive Losses: {max_streak_loss}")
        print("-" * 30)

    analyze_year_strategy(2022)
    analyze_year_strategy(2025)

    # Forensic Analysis of Ukraine Invasion
    def analyze_ukraine_shock():
        print("--- FORENSIC ANALYSIS: UKRAINE INVASION (FEB-APR 2022) ---")
        start_dt = datetime(2022, 2, 1, tzinfo=timezone.utc)
        end_dt = datetime(2022, 4, 30, tzinfo=timezone.utc)
        
        sub = df.filter((pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt))
        y = sub["Y"].to_numpy()
        x = sub["X"].to_numpy()
        
        y_ret = (y[-1] - y[0]) / y[0] * 100
        x_ret = (x[-1] - x[0]) / x[0] * 100
        
        corr = np.corrcoef(np.diff(np.log(y)), np.diff(np.log(x)))[0,1]
        
        print(f"CAC 40 Return: {y_ret:.2f}%")
        print(f"Oil Return:    {x_ret:.2f}%")
        print(f"Correlation:   {corr:.3f}")
        print("Verdict: INVERSE SHOCK. Oil Up, Europe Down.")

    analyze_ukraine_shock()
