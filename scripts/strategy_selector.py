
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def select_strategy(pair_name="EUR/GBP", file_x="EURUSD_15m.parquet", file_y="GBPUSD_15m.parquet", col_x="close_EURUSD", col_y="close_GBPUSD", year=2025):
    print(f"\n--- STRATEGY SELECTOR: {pair_name} ({year}) ---")
    
    # Load Data
    p_x = os.path.join(DATA_DIR, file_x)
    p_y = os.path.join(DATA_DIR, file_y)
    
    df_x = pl.read_parquet(p_x).rename({col_x: "X"})
    df_y = pl.read_parquet(p_y).rename({col_y: "Y"})
    
    df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == year)
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    # Calculate Returns Volatility
    y_ret = np.diff(y)
    x_ret = np.diff(x)
    vol_y = np.std(y_ret)
    vol_x = np.std(x_ret)
    
    vol_ratio = vol_y / vol_x
    
    print(f"Volatility Ratio (Y/X): {vol_ratio:.4f}")
    
    if vol_ratio > 1.0:
        high_vol = "Y (Target)"
        low_vol = "X (Predictor)"
        high_name = col_y.split('_')[1]
        low_name = col_x.split('_')[1]
    else:
        high_vol = "X (Predictor)"
        low_vol = "Y (Target)"
        high_name = col_x.split('_')[1]
        low_name = col_y.split('_')[1]

    print(f"High Volatility Leg ('The Whip'): {high_name}")
    print(f"Low Volatility Leg  ('The Tank'): {low_name}")
    print("-" * 30)
    print("RECOMMENDED STRATEGY MAP:")
    print(f"1. **{high_name}** -> MEAN REVERSION (Fade Z).")
    print(f"   (Reason: It creates the noise. Bet on it snapping back.)")
    print(f"2. **{low_name}** -> MOMENTUM (Follow Z).")
    print(f"   (Reason: It creates the drift. Bet on it breaking out.)")
    print("-" * 30)

if __name__ == "__main__":
    select_strategy(year=2025)
    select_strategy(year=2024)
