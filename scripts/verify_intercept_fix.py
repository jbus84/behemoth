
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_4h"
Y_SYM = "FRXEUR"
X_SYM = "AUDCAD"

def test_intercept_hypothesis():
    print(f"--- INTERCEPT HYPOTHESIS CHECK: {Y_SYM}/{X_SYM} ---")

    # Load Data
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_4h.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_4h.parquet"))
    except:
        print("Data not found."); return

    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).sort("timestamp")

    # 2025 Data
    df = df.filter(pl.col("timestamp").dt.year() == 2025)

    y_raw = np.log(df["Y"].to_numpy())
    x_raw = np.log(df["X"].to_numpy())

    print(f"Mean Y (Log): {np.mean(y_raw):.4f}")
    print(f"Mean X (Log): {np.mean(x_raw):.4f}")
    print(f"Implied Intercept/Beta = Y/X = {np.mean(y_raw)/np.mean(x_raw):.2f}")

    # 1. Uncentered (Original Bug)
    print("\n--- TEST 1: UNCENTERED (Original) ---")
    kf1 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas1 = []
    for i in range(len(y_raw)):
        b, _ = kf1.update(x_raw[i], y_raw[i])
        betas1.append(b)
    print(f"Avg Beta: {np.mean(betas1):.4f}")

    # 2. Centered (Fixed)
    print("\n--- TEST 2: CENTERED (Global Mean Removed) ---")
    y_centered = y_raw - np.mean(y_raw)
    x_centered = x_raw - np.mean(x_raw)

    kf2 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas2 = []
    for i in range(len(y_centered)):
        b, _ = kf2.update(x_centered[i], y_centered[i])
        betas2.append(b)
    print(f"Avg Beta: {np.mean(betas2):.4f}")

    # 3. Rolling Centered (Robust)
    print("\n--- TEST 3: ROLLING CENTERED (Window=500) ---")
    # Simulate real-time by subtracting moving average
    kf3 = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas3 = []

    y_window = []
    x_window = []

    for i in range(len(y_raw)):
        # Update windows
        y_window.append(y_raw[i])
        x_window.append(x_raw[i])
        if len(y_window) > 500: y_window.pop(0); x_window.pop(0)

        # Center using current window mean
        y_curr = y_raw[i] - np.mean(y_window)
        x_curr = x_raw[i] - np.mean(x_window)

        b, _ = kf3.update(x_curr, y_curr)
        betas3.append(b)

    print(f"Avg Beta: {np.mean(betas3):.4f}")

    if abs(np.mean(betas3)) < 10.0:
        print("\nVERDICT: CONFIRMED. Centering fixes the 'Beta 80' bug.")
        print("The huge beta was compensating for the missing intercept.")
    else:
        print("\nVERDICT: UNCERTAIN. Betas still high.")

if __name__ == "__main__":
    test_intercept_hypothesis()
