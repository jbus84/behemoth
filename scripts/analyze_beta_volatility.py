
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil (Stable Winner)"),
    ("USDCHF", "GRXEUR", "CHF/DAX (Regime Loser)"),
    ("XAUUSD", "BCOUSD", "Gold/Oil (Volatile Winner)"),
]

def analyze_beta_volatility():
    print("--- DYNAMIC REGIME DETECTION: BETA VOLATILITY (2024) ---")
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

            # Centered Kalman
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            betas = []
            y_win, x_win = [], []

            for i in range(len(y)):
                y_win.append(y[i]); x_win.append(x[i])
                if len(y_win)>500: y_win.pop(0); x_win.pop(0)
                if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
                else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)

                b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
                betas.append(b)

            # Analysis: Rolling Beta Volatility (Window 50)
            beta_vol = []
            bs = np.array(betas)
            for i in range(50, len(bs)):
                window = bs[i-50:i]
                # Normalized Volatility (CV): Std / Mean (to account for beta scale)
                # Or just raw change? Let's try raw change magnitude first.
                # Actually, "Velocity of Beta" might be better: sum(abs(diff(beta)))

                velocity = np.mean(np.abs(np.diff(window)))
                beta_vol.append(velocity)

            avg_vel = np.mean(beta_vol) * 1000 # Scale up
            max_vel = np.max(beta_vol) * 1000

            print(f"[{label}]")
            print(f"  Beta Velocity (Mean): {avg_vel:.4f}")
            print(f"  Beta Velocity (Max):  {max_vel:.4f}")
            print("-" * 30)

        except Exception as e:
            print(f"Error {label}: {e}")

if __name__ == "__main__":
    analyze_beta_volatility()
