
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil (Stable Winner)"),
    ("USDCHF", "GRXEUR", "CHF/DAX (Regime Loser)"),
]

def calculate_hurst(ts):
    """Returns the Hurst Exponent of the time series vector ts"""
    lags = range(2, 20)
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0]*2.0

def analyze_hurst():
    print("--- DYNAMIC REGIME DETECTION: ROLLING HURST (2024) ---")
    start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2024, 12, 31, tzinfo=timezone.utc)

    for y_sym, x_sym, label in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")

        try:
            df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
            df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

            df = df_y.join(df_x, on="timestamp", how="inner").filter(
                (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
            ).sort("timestamp")

            y = np.log(df["Y"].to_numpy())
            x = np.log(df["X"].to_numpy())

            # Kalman Residuals
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            errors = []
            y_win, x_win = [], []

            for i in range(len(y)):
                y_win.append(y[i]); x_win.append(x[i])
                if len(y_win)>500: y_win.pop(0); x_win.pop(0)
                if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
                else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)

                b, res = kf.update(x[i]-mu_x, y[i]-mu_y)
                errors.append(res)

            # Rolling Hurst (Window 100)
            hursts = []
            err_arr = np.array(errors)

            # We need at least 100 bars for Hurst
            for i in range(100, len(err_arr)):
                window = err_arr[i-100:i]
                # Simplified Hurst (Empirical)
                # Using R/S analysis is slow. Using Jagged Variance is faster.
                # Let's try the simplified lag variance method defined above.
                h = calculate_hurst(window)
                hursts.append(h)

            hursts = np.array(hursts)

            mean_h = np.mean(hursts)
            percent_bad = np.mean(hursts > 0.5) * 100

            print(f"[{label}]")
            print(f"  Mean Hurst:     {mean_h:.3f}")
            print(f"  % Time > 0.5:   {percent_bad:.1f}%")
            print(f"  (Low Hurst = Mean Reverting. High Hurst = Trending/Random)")
            print("-" * 30)

        except Exception as e:
            print(f"Error {label}: {e}")

if __name__ == "__main__":
    analyze_hurst()
