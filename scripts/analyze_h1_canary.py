
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"

def analyze_h1_canary():
    print("--- H1 CANARY ANALYSIS (FRX/BCO) ---")

    p_y = os.path.join(DATA_DIR, "FRXEUR_1h.parquet")
    p_x = os.path.join(DATA_DIR, "BCOUSD_1h.parquet")

    df_y = pl.read_parquet(p_y).rename({"close_FRXEUR": "Y"})
    df_x = pl.read_parquet(p_x).rename({"close_BCOUSD": "X"})

    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

    def run_year(year):
        start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(year, 12, 31, tzinfo=timezone.utc)

        sub = df.filter((pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt))
        y = np.log(sub["Y"].to_numpy())
        x = np.log(sub["X"].to_numpy())

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

        stops = 0
        technical_breaks = 0
        total_bars = len(y) - 500

        in_pos = 0

        for i in range(500, len(y)):
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std

            # Count "Technical Breaks" (Z > 3.5) regardless of position
            if abs(z) > 3.5:
                technical_breaks += 1

            if in_pos == 0:
                if z > 1.5: in_pos = -1
                elif z < -1.5: in_pos = 1
            elif in_pos == 1:
                if z > 0.0: in_pos = 0
                elif z < -3.5: in_pos = 0; stops += 1
            elif in_pos == -1:
                if z < 0.0: in_pos = 0
                elif z > 3.5: in_pos = 0; stops += 1

        print(f"[{year}]")
        print(f"  Technical Breaks (Z>3.5): {technical_breaks}")
        print(f"  Actual Stop Hits:         {stops}")
        print("-" * 30)

    run_year(2022)
    run_year(2025)

if __name__ == "__main__":
    analyze_h1_canary()
