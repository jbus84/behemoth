
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_4h"
Y_SYM = "FRXEUR"
X_SYM = "AUDCAD"

def debug_z_scores():
    print(f"--- Z-SCORE DIAGNOSTIC ({Y_SYM}/{X_SYM}) ---")

    # Load 2025 Data
    df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_4h.parquet"))
    df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_4h.parquet"))

    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).filter(
        pl.col("timestamp").dt.year() == 2025
    ).sort("timestamp")

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    y_win, x_win = [], []

    for i in range(len(y)):
        y_win.append(y[i])
        x_win.append(x[i])
        if len(y_win) > 500: y_win.pop(0); x_win.pop(0)

        mu_y = np.mean(y_win)
        mu_x = np.mean(x_win)

        y_c = y[i] - mu_y
        x_c = x[i] - mu_x

        b, _ = kf.update(x_c, y_c)
        betas.append(b)
        errors.append(y_c - b * x_c)

    z_scores = []

    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu = np.mean(window)
        std = np.std(window)
        if std < 1e-9: continue
        z = (errors[i] - mu) / std
        z_scores.append(z)

    z_scores = np.array(z_scores)

    print(f"Total Bars: {len(z_scores)}")
    print(f"Z-Score Stats:")
    print(f"  Mean: {np.mean(z_scores):.4f}")
    print(f"  Std:  {np.std(z_scores):.4f}")
    print(f"  Max:  {np.max(z_scores):.4f}")
    print(f"  Min:  {np.min(z_scores):.4f}")

    gt_2 = np.sum(np.abs(z_scores) > 2.0)
    gt_15 = np.sum(np.abs(z_scores) > 1.5)

    print(f"Bars > 2.0: {gt_2}")
    print(f"Bars > 1.5: {gt_15}")

    print(f"Avg Beta: {np.mean(betas):.4f}")

if __name__ == "__main__":
    debug_z_scores()
