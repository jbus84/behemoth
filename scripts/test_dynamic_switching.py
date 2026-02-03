
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def backtest_dynamic_switching(year):
    print(f"--- DYNAMIC SWITCHING TEST ({year}) ---")
    
    # Load Data
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == year)
    
    y = np.log(df["Y"].to_numpy()) # GBP
    x = np.log(df["X"].to_numpy()) # EUR
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    errors = []
    
    # Pre-calculate Kalman State
    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)
        errors.append((y[i]-mu_y) - b*(x[i]-mu_x))
        
    thresh = 2.0
    stop_level = 3.5
    COST_BPS_GBP = 1.6
    COST_BPS_EUR = 1.0
    
    total_pnl = 0.0
    trades = 0
    
    in_pos = 0 # 1=Long, -1=Short
    active_asset = None # 'EUR' or 'GBP'
    strategy_type = None # 'REV' or 'MOM'
    entry_price = 0.0
    
    # Strategy Logic:
    # We check Beta[i] to decide WHO to trade and HOW.
    # Beta < 0.95: EUR is Whip (High Vol). Trade EUR Reversion.
    # Beta > 1.05: GBP is Whip (High Vol). Trade GBP Reversion.
    # What about the Tank (Momentum)?
    # Let's pick the BEST strategy for each regime.
    # 2025 (Beta < 1): EUR Rev (+764), GBP Mom (+835). Both Work using Whip/Tank rule.
    # 2024 (Beta > 1): GBP Rev (-210), EUR Mom (+120). Tank Mom worked best.
    
    # Hypothesis: Use "Tank Momentum" as the Primary Strategy.
    # It worked in 2025 (GBP Mom) and 2024 (EUR Mom).
    # Rule:
    # If Beta < 1 (EUR=Whip, GBP=Tank): Trade GBP Momentum.
    # If Beta > 1 (GBP=Whip, EUR=Tank): Trade EUR Momentum.
    
    print(f"Strategy Rule: Trade MOMENTUM on the Low Volatility Leg (The Tank).")
    print("| Threshold | Net PnL (bps) | Trades |")
    print("|---|---|---|")
    
    for thresh in [1.5, 2.0, 2.5]:
        total_pnl = 0.0
        trades = 0
        
        in_pos = 0 # 1=Long, -1=Short
        active_asset = None # 'EUR' or 'GBP'
        entry_price = 0.0
        
        stop_level = max(3.5, thresh + 1.0)
        
        for i in range(500, len(y)):
            beta = betas[i]
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            
            # Determine Regime
            if beta < 0.98: # EUR High Vol / GBP Low Vol
                target_asset = 'GBP' 
            elif beta > 1.02: # GBP High Vol / EUR Low Vol
                target_asset = 'EUR'
            else:
                target_asset = 'NEUTRAL'
                
            current_price_gbp = y[i]
            current_price_eur = x[i]
            
            # Execution
            if in_pos == 0:
                if target_asset == 'GBP':
                    if z > thresh: in_pos = 1; active_asset = 'GBP'; entry_price = current_price_gbp
                    elif z < -thresh: in_pos = -1; active_asset = 'GBP'; entry_price = current_price_gbp
                
                elif target_asset == 'EUR':
                    if z > thresh: in_pos = -1; active_asset = 'EUR'; entry_price = current_price_eur
                    elif z < -thresh: in_pos = 1; active_asset = 'EUR'; entry_price = current_price_eur
            
            elif in_pos != 0:
                pnl = 0.0
                closed = False
                
                if active_asset == 'GBP':
                    if in_pos == 1:
                        if z < 0: # Reverted (Loss)
                             gross = current_price_gbp - entry_price
                             pnl = (gross * 10000) - COST_BPS_GBP
                             closed = True
                        elif z > stop_level: # Trend (Win)
                             gross = current_price_gbp - entry_price
                             pnl = (gross * 10000) - COST_BPS_GBP
                             closed = True
                    
                    elif in_pos == -1: # Short GBP (Z Low)
                        if z > 0: # Reverted (Loss)
                            gross = -(current_price_gbp - entry_price)
                            pnl = (gross * 10000) - COST_BPS_GBP
                            closed = True
                        elif z < -stop_level: # Trend (Win)
                            gross = -(current_price_gbp - entry_price)
                            pnl = (gross * 10000) - COST_BPS_GBP
                            closed = True

                elif active_asset == 'EUR':
                    if in_pos == -1: # Short EUR
                         if z < 0: # Reverted (Loss)
                             gross = -(current_price_eur - entry_price)
                             pnl = (gross * 10000) - COST_BPS_EUR
                             closed = True
                         elif z > stop_level: # Trend (Win)
                             gross = -(current_price_eur - entry_price)
                             pnl = (gross * 10000) - COST_BPS_EUR
                             closed = True
                    
                    elif in_pos == 1: # Long EUR (Z was Low)
                        if z > 0: # Reverted (Loss)
                            gross = current_price_eur - entry_price
                            pnl = (gross * 10000) - COST_BPS_EUR
                            closed = True
                        elif z < -stop_level: # Trend (Win)
                            gross = current_price_eur - entry_price
                            pnl = (gross * 10000) - COST_BPS_EUR
                            closed = True
                
                if closed:
                    total_pnl += pnl
                    trades += 1
                    in_pos = 0; active_asset = None
                    
        print(f"| {thresh} | {total_pnl:.1f} | {trades} |")

if __name__ == "__main__":
    backtest_dynamic_switching(2025)
    backtest_dynamic_switching(2024)
