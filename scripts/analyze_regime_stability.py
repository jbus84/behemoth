
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil (Winner)"),
    ("USDCHF", "GRXEUR", "CHF/DAX (Loser)"),
    ("XAUUSD", "BCOUSD", "Gold/Oil (Winner)"),
    ("FRXEUR", "EURGBP", "CAC/EURGBP (Winner)"),
    ("UDXUSD", "GRXEUR", "USD/DAX (Loser)"),
    ("AUDUSD", "USDCAD", "AUD/CAD (Control)"),
]

def analyze_stability():
    print("--- REGIME STABILITY ANALYSIS (2024) ---")
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

            # 1. Calculate Centered Beta (Signal)
            kf_c = KalmanFilterReg(Q=1e-5, R=1e-3)
            betas_c = []
            y_win, x_win = [], []

            for i in range(len(y)):
                y_win.append(y[i]); x_win.append(x[i])
                if len(y_win)>500: y_win.pop(0); x_win.pop(0)

                if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
                else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)

                b, _ = kf_c.update(x[i]-mu_x, y[i]-mu_y)
                betas_c.append(b)

            # 2. Calculate Returns Beta (Hedge)
            # Use Rolling OLS on diffs (Window 60)
            dy = np.diff(y)
            dx = np.diff(x)
            betas_r = [0.0]*len(y)

            for i in range(60, len(dy)):
                # Simple OLS on window
                win_dy = dy[i-60:i]
                win_dx = dx[i-60:i]
                var_x = np.var(win_dx)
                if var_x > 1e-9:
                    cov = np.cov(win_dx, win_dy)[0,1]
                    betas_r[i+1] = cov / var_x
                else:
                    betas_r[i+1] = betas_r[i]

            # 3. Analyze Stability Ratio
            # Skip first 500 bars warmup
            ratios = []
            for i in range(500, len(y)):
                bc = betas_c[i]
                br = betas_r[i]
                if abs(br) > 0.01:
                    ratios.append(bc / br)

            # Stats
            r = np.array(ratios)
            # Filter outliers for clean mean
            r = r[np.abs(r) < 5.0]

            mean_r = np.mean(np.abs(r)) # USE ABSOLUTE
            std_r = np.std(r)

            print(f"[{label}]")
            print(f"  Abs Ratio:  {mean_r:.3f}")
            print(f"  Std Dev:    {std_r:.3f}")
            print(f"  Converged?  {0.8 < mean_r < 1.2 and std_r < 0.3}")
            print("-" * 30)

        except Exception as e:
            print(f"Error {label}: {e}")

if __name__ == "__main__":
    analyze_stability()
