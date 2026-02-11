
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil"),
    ("XAUUSD", "BCOUSD", "Gold/Oil"),
]

def analyze_duration():
    print("--- 2025 TRADE DURATION ANALYSIS (H4) ---")

    for y_sym, x_sym, label in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")

        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

        # 2025 Only
        start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        sub = df.filter(pl.col("timestamp") >= start_dt)

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

        durations = []
        entry_idx = -1
        in_pos = 0 # 0, 1, -1

        for i in range(500, len(y)):
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std

            if in_pos == 0:
                if z > 1.5: in_pos = -1; entry_idx = i
                elif z < -1.5: in_pos = 1; entry_idx = i
            elif in_pos == 1:
                # Exit conditions
                if z > 0.0 or z < -3.5: # Mean Revert or Stop
                    durations.append(i - entry_idx)
                    in_pos = 0
            elif in_pos == -1:
                if z < 0.0 or z > 3.5:
                    durations.append(i - entry_idx)
                    in_pos = 0

        if len(durations) > 0:
            avg_bars = np.mean(durations)
            avg_days = (avg_bars * 4) / 24
            max_days = (np.max(durations) * 4) / 24
            print(f"[{label}]")
            print(f"  Avg Duration: {avg_bars:.1f} bars (~{avg_days:.1f} days)")
            print(f"  Max Duration: {np.max(durations)} bars (~{max_days:.1f} days)")
            print(f"  Trades:       {len(durations)}")
            print("-" * 30)

if __name__ == "__main__":
    analyze_duration()
