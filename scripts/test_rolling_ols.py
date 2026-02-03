
import polars as pl
import numpy as np
import os
from sklearn.linear_model import LinearRegression

DATA_DIR = "data/global_1h"
Y_SYM = "BCOUSD"
X_SYM = "GRXEUR"
COST_BPS = 9.0
WINDOW = 300 # 300 Hours (~12 Days)

def test_rolling_ols():
    print(f"--- ROLLING OLS AUDIT: {Y_SYM}/{X_SYM} (H1) ---")
    print(f"Window: {WINDOW} Bars")
    
    # Load
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_1h.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_1h.parquet"))
    except: return

    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).sort("timestamp")
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    betas = []
    spreads = []
    
    # Rolling OLS Loop
    # We will simulate OLS computed at t-1 applied to t
    
    for i in range(len(y)):
        if i < WINDOW:
            betas.append(0)
            spreads.append(0)
            continue
            
        y_win = y[i-WINDOW:i].reshape(-1, 1) # Training Data (Past)
        x_win = x[i-WINDOW:i].reshape(-1, 1)
        
        reg = LinearRegression().fit(x_win, y_win)
        beta = reg.coef_[0][0]
        
        # Current Spread using OLD Beta vs CURRENT Price
        # spread = y_t - beta * x_t - intercept
        # Wait, usually we center spread. 
        # residual = y - beta*x - intercept
        intercept = reg.intercept_[0]
        
        current_spread = y[i] - beta * x[i] - intercept
        
        betas.append(beta)
        spreads.append(current_spread)
        
    # Trading Loop (Real PnL)
    real_pnls = []
    in_pos = 0
    entry_val = 0.0
    entry_beta = 0.0
    entry_y = 0.0
    entry_x = 0.0
    
    trades = 0
    z_scores = []
    
    # Calc Z-Scores first (Rolling Std of spreads)
    spread_arr = np.array(spreads)
    
    for i in range(WINDOW+50, len(y)):
        # Z-Score of the current spread relative to its recent history?
        # The spread is already a residual. It should be mean 0.
        # But let's normalize by std dev of the spread over last 100 bars.
        
        hist_spreads = spread_arr[i-100:i]
        std = np.std(hist_spreads)
        if std < 1e-6: continue
        
        curr_spread = spread_arr[i]
        z = curr_spread / std
        
        # Trading
        # If Spread > 2 std dev, Short Spread (Short Y, Long Beta*X)
        
        if in_pos == 0:
            if z > 2.0:
                in_pos = -1 # Short Spread
                entry_beta = betas[i]
                entry_y = y[i]
                entry_x = x[i]
            elif z < -2.0:
                in_pos = 1 # Long Spread
                entry_beta = betas[i]
                entry_y = y[i]
                entry_x = x[i]
                
        elif in_pos == 1: # Long Y
            if z > 0.0 or z < -3.0: # Exit
                pnl_y = y[i] - entry_y
                pnl_x = entry_beta * (x[i] - entry_x)
                real_pnl = (pnl_y - pnl_x) * 10000 - COST_BPS
                real_pnls.append(real_pnl)
                in_pos = 0
                trades += 1
                
        elif in_pos == -1: # Short Y
            if z < 0.0 or z > 3.0: # Exit
                pnl_y = -(y[i] - entry_y)
                pnl_x = entry_beta * (x[i] - entry_x)
                real_pnl = (pnl_y + pnl_x) * 10000 - COST_BPS
                real_pnls.append(real_pnl)
                in_pos = 0
                trades += 1
                
    # Stats
    pnls = np.array(real_pnls)
    if len(pnls) > 0:
        win_rate = np.mean(pnls > 0) * 100
        avg_pnl = np.mean(pnls)
        print(f"Trades: {trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Avg Real PnL: {avg_pnl:.2f} bps")
        
        if avg_pnl > 0:
            print("VERDICT: PASS. Rolling OLS works.")
        else:
            print("VERDICT: FAIL. Even OLS fails.")
    else:
        print("No trades.")

if __name__ == "__main__":
    test_rolling_ols()
