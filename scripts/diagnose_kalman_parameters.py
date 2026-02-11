
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def diagnose_pair(pair_name, file_x, file_y, col_x, col_y):
    print(f"\n--- DIAGNOSING {pair_name} ---")

    p_x = os.path.join(DATA_DIR, file_x)
    p_y = os.path.join(DATA_DIR, file_y)

    df_x = pl.read_parquet(p_x).rename({col_x: "X"})
    df_y = pl.read_parquet(p_y).rename({col_y: "Y"})

    df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == 2025)

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []

    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)

    avg_beta = np.mean(betas)
    print(f"Avg Kalman Beta: {avg_beta:.4f}")

    if avg_beta < 1.0:
        # Beta < 1 => y = 0.8x => x moves MORE than y.
        # X is the High Vol leg.
        print(f"Structure: X ({col_x.split('_')[1]}) is High Volatility.")
        print(f"Structure: Y ({col_y.split('_')[1]}) is Low Volatility.")
        print("Recommendation:")
        print(f"  - Trade X for MEAN REVERSION (Catches the noise).")
        print(f"  - Trade Y for MOMENTUM (Rides the drift).")
    else:
        # Beta > 1 => y = 2.0x => y moves MORE than x.
        # Y is the High Vol leg.
        print(f"Structure: Y ({col_y.split('_')[1]}) is High Volatility.")
        print(f"Structure: X ({col_x.split('_')[1]}) is Low Volatility.")
        print("Recommendation:")
        print(f"  - Trade Y for MEAN REVERSION (Catches the noise).")
        print(f"  - Trade X for MOMENTUM (Rides the drift).")

if __name__ == "__main__":
    # Test EUR/GBP
    diagnose_pair("EUR/GBP", "EURUSD_15m.parquet", "GBPUSD_15m.parquet", "close_EURUSD", "close_GBPUSD")

    # Test Gold/Oil (Just to see)
    # diagnose_pair("Gold/Oil", "XAUUSD_15m.parquet", "BCOUSD_15m.parquet", "close_XAUUSD", "close_BCOUSD")
