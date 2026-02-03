
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def backtest_cable_shadow():
    print("--- CABLE SHADOW TRADE (SINGLE LEG M15) ---")
    print("Strategy: Calculate Signal from EUR/GBP. Trade ONLY GBP.")
    
    # Load Data
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"}) # Predictor (Anchor)
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"}) # Target (The Beast)
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    
    # Remove 2025 filter, keep all data
    # (Data is already loaded)
    
    y_full = np.log(df["Y"].to_numpy()) # GBP
    x_full = np.log(df["X"].to_numpy()) # EUR
    ts_full = df["timestamp"].to_numpy()
    
    # Kalman Filter (Run once on full history for state continuity)
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    
    for i in range(len(y_full)):
        if i < 10: mu_y, mu_x = y_full[i], x_full[i]
        else: mu_y, mu_x = np.mean(y_full[max(0,i-500):i]), np.mean(x_full[max(0,i-500):i])
        b, _ = kf.update(x_full[i]-mu_x, y_full[i]-mu_y)
        betas.append(b)
        errors.append((y_full[i]-mu_y) - b*(x_full[i]-mu_x))
        
    print(f"\n--- INVERTED STRATEGY (MOMENTUM) AUDIT [Z=2.0] ---")
    print("| Year | Net PnL (bps) | Trades | Win Rate |")
    print("|---|---|---|---|")
    
    thresh = 2.0
    stop_level = 3.5
    COST_BPS = 1.6
    
    results = {}
    total_pnl = 0.0
    
    years = range(2018, 2026)
    
    # We need to segment by year for reporting
    # Identify indices for each year to be efficient or just check timestamp in loop
    
    current_year = -1
    year_pnl = 0.0
    year_trades = 0
    year_wins = 0
    
    in_pos = 0 
    entry_price = 0.0
    
    for i in range(500, len(y_full)):
        ts_i = ts_full[i]
        yr = ts_i.astype('datetime64[Y]').astype(int) + 1970
        
        if yr != current_year:
            if current_year != -1:
                wr = year_wins/year_trades*100 if year_trades > 0 else 0
                print(f"| {current_year} | {year_pnl:.1f} | {year_trades} | {wr:.1f}% |")
                total_pnl += year_pnl
            current_year = yr
            year_pnl = 0.0
            year_trades = 0
            year_wins = 0
            # Reset position on year boundary? No, let it ride.
            
        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std
        
        pnl_inv = 0.0
        
        if in_pos == 0:
            if z > thresh: 
                # Z High -> GBP Expensive.
                # Inverted Logic: BUY GBP (Bet on Breakout)
                in_pos = 1; entry_price = y_full[i]
            elif z < -thresh:
                # Z Low -> GBP Cheap.
                # Inverted Logic: SELL GBP (Bet on Crash)
                in_pos = -1; entry_price = y_full[i]
                
        elif in_pos == 1: # Long GBP
            if z > stop_level: # Continued Breakout (Profit Take?) 
                # Wait, standard stop is Z < -3.5. 
                # In Momentum:
                # We entered Long at Z > 2.0.
                # If Z drops < 0.0 (Reversion), we LOSE.
                # If Z goes > 3.5 (Extreme), we WIN BIG.
                # Exit condition: Reversion to Mean (Z crosses 0).
                pass 
            
            # Simplified Momentum Logic:
            # We hold until Z reversion (Z=0).
            # If Z=0, the deviation is gone. Momentum is over.
            # In Mean Reversion, Z=0 is profit.
            # In Momentum, Z=0 is LOSS (because price moved back).
            # So, Inverted PnL calculation handles the math automatically.
            
            if z < 0.0: # Reverted (Momentum Failed/ended)
                gross = y_full[i] - entry_price # Standard Long PnL
                # Inverted PnL = -Gross - Cost
                # Wait. If I Long GBP and price goes UP (Z goes higher), Gross is Positive.
                # Standard Logic: Enter Short at Z>2.
                # Inverted Logic: Enter Long at Z>2.
                
                # Let's trust the math:
                # Standard Trade: Short GBP.
                # If Z -> 0 (Price Drops), Standard Wins. Inverted Loses.
                # If Z -> 3.5 (Price Rises), Standard Stops. Inverted Wins.
                
                # Exit at Z < 0.0 (Standard Win condition)
                gross_std = -(y_full[i] - entry_price) # Short PnL
                pnl_inv = (-gross_std * 10000) - COST_BPS
                
                in_pos = 0; year_trades += 1
                if pnl_inv > 0: year_wins += 1
                
            elif z > 3.5: # Extreme (Momentum moves further)
                # Standard Stop Loss
                gross_std = -(y_full[i] - entry_price) # Short PnL (Loss)
                pnl_inv = (-gross_std * 10000) - COST_BPS # Inverted Profit
                
                in_pos = 0; year_trades += 1
                if pnl_inv > 0: year_wins += 1
                
        elif in_pos == -1: # Short GBP
             # We entered Short at Z < -2.0.
             if z > 0.0: # Reverted
                 gross_std = y_full[i] - entry_price # Long PnL
                 pnl_inv = (-gross_std * 10000) - COST_BPS
                 in_pos = 0; year_trades += 1
                 if pnl_inv > 0: year_wins += 1
             elif z < -3.5: # Extreme Crash
                 gross_std = y_full[i] - entry_price # Long PnL (Loss)
                 pnl_inv = (-gross_std * 10000) - COST_BPS
                 in_pos = 0; year_trades += 1
                 if pnl_inv > 0: year_wins += 1

        year_pnl += pnl_inv
        
    # Print last year
    if current_year != -1:
        wr = year_wins/year_trades*100 if year_trades > 0 else 0
        print(f"| {current_year} | {year_pnl:.1f} | {year_trades} | {wr:.1f}% |")
        total_pnl += year_pnl

    print(f"| **TOTAL** | **{total_pnl:.0f}** | | |")

if __name__ == "__main__":
    backtest_cable_shadow()
