
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"

# The Oil/DAX Pair
Y_SYM = "BCOUSD"
X_SYM = "GRXEUR"
COST_BPS = 0.0009 # 9 basis points (REAL COST found in validation)

def validate_h1_survival():
    print(f"\n--- VALIDATING H1 SURVIVAL ({Y_SYM}/{X_SYM}) ---")
    print(f"Cost Model: {COST_BPS*10000:.1f} bps (Severe)")
    
    # Load Data
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_1h.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_1h.parquet"))
    except Exception as e:
        print(f"Data not found: {e}")
        return

    # Align
    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).sort("timestamp")
    
    # Kalman Setup
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    y_vals = np.log(df["Y"].to_numpy())
    x_vals = np.log(df["X"].to_numpy())
    
    pnls = []
    in_position = 0
    entry_val = 0.0
    
    # Arrays for speed
    betas = []
    errors = []
    
    # Warmup
    for i in range(len(y_vals)):
        b, err = kf.update(x_vals[i], y_vals[i])
        betas.append(b)
        # Recalc spread explicitly: Y - b*X (centered)
        errors.append(y_vals[i] - b * x_vals[i])
        
    trades = 0
    
    # Trading Loop
    for i in range(500, len(y_vals)):
        # Z-Score
        window = errors[i-500:i]
        mu = np.mean(window)
        std = np.std(window)
        
        current_spread = errors[i]
        if std < 1e-6: z = 0
        else: z = (current_spread - mu) / std
        
        # Logic
        if in_position == 0:
            if z > 2.0:
                in_position = -1
                entry_val = current_spread
                pnls.append(-COST_BPS) # Entry Cost
                trades += 1
            elif z < -2.0:
                in_position = 1
                entry_val = current_spread
                pnls.append(-COST_BPS) # Entry Cost
                trades += 1
        elif in_position == 1:
            if z > 0.0 or z < -4.0:
                pnl = current_spread - entry_val
                pnls.append(pnl - COST_BPS) # Exit Cost
                in_position = 0
        elif in_position == -1:
            if z < 0.0 or z > 4.0:
                pnl = entry_val - current_spread
                pnls.append(pnl - COST_BPS) # Exit Cost
                in_position = 0
                
    # Stats
    total_pnl = np.sum(pnls)
    if trades > 0:
        avg_trade_bps = (total_pnl / trades) * 10000
    else:
        avg_trade_bps = 0
        
    print(f"Total Trades: {trades}")
    print(f"Total Return (Log Points): {total_pnl:.4f}")
    print(f"Avg Net Profit per Trade: {avg_trade_bps:.2f} bps")
    
    if avg_trade_bps > 0:
        print("VERDICT: PASS (H1 Survives Costs)")
    else:
        print("VERDICT: FAIL (H1 Dies too)")

if __name__ == "__main__":
    validate_h1_survival()
