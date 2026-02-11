
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", 9.0, "CAC/Oil"),
    ("XAUUSD", "BCOUSD", 10.0, "Gold/Oil"),
]

def run_vol_analysis(y_sym, x_sym, cost_bps, label):
    p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
    p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")

    try:
        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

        y_log = np.log(df["Y"].to_numpy())
        x_log = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        # 1. Run Kalman
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []
        y_win, x_win = [], []

        for i in range(len(y_log)):
            y_win.append(y_log[i]); x_win.append(x_log[i])
            if len(y_win)>500: y_win.pop(0); x_win.pop(0)
            if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
            else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
            b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
            betas.append(b)
            errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))

        # 2. Slice by Year
        years = range(2018, 2026)
        results = {}
        vol_stats = {}

        in_pos = 0
        entry_beta, entry_y, entry_x = 0., 0., 0.

        for i in range(500, len(y_log)):
            dt = ts[i]
            yr = dt.astype('datetime64[Y]').astype(int) + 1970

            # Volatility Calculation (Window 100)
            # Use Rolling Std Dev of Y Log Returns as proxy for market "Heat"
            if i > 600:
                vol_window = np.diff(y_log[i-100:i])
                vol = np.std(vol_window) * 1000 # Scale up
            else:
                vol = 0

            # Track Annual Vol
            if yr not in vol_stats: vol_stats[yr] = []
            vol_stats[yr].append(vol)

            # Strategy Logic
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std
            beta = betas[i-1]

            pnl = 0.0
            if in_pos == 0:
                if z > 1.5: in_pos = -1; entry_beta=beta; entry_y=y_log[i]; entry_x=x_log[i]
                elif z < -1.5: in_pos = 1; entry_beta=beta; entry_y=y_log[i]; entry_x=x_log[i]
            elif in_pos == 1:
                if z > 0.0 or z < -2.0:
                    gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                    pnl = gross * 10000 - cost_bps
                    in_pos = 0
            elif in_pos == -1:
                if z < 0.0 or z > 2.0:
                    gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                    pnl = gross * 10000 - cost_bps
                    in_pos = 0

            if yr not in results: results[yr] = []
            if pnl != 0.0: results[yr].append(pnl)

        print(f"\n--- {label} Annual Analysis ---")
        print("| Year | PnL (bps) | Avg Volatility |")
        print("|---|---|---|")

        for yr in years:
            pnl = sum(results.get(yr, []))
            vols = vol_stats.get(yr, [0])
            avg_vol = np.mean(vols)
            print(f"| {yr} | {pnl:.0f} | {avg_vol:.2f} |")

    except Exception as e:
        print(f"Error {label}: {e}")

if __name__ == "__main__":
    for y, x, c, l in PAIRS:
        run_vol_analysis(y, x, c, l)
