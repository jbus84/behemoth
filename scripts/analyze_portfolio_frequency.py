
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_4h"

PAIRS = [
    # Tier 1
    ("FRXEUR", "BCOUSD", "CAC/Oil"),
    ("USDCHF", "GRXEUR", "Swiss/DAX"),
    ("XAUUSD", "BCOUSD", "Gold/Oil"),
    ("FRXEUR", "EURGBP", "CAC/EURGBP"),
    # Tier 2
    ("UDXUSD", "GRXEUR", "USD/DAX"),
    ("FRXEUR", "USDJPY", "CAC/Yen"),
    ("EURUSD", "EURJPY", "Euro/Yen"),
    ("BCOUSD", "XAGUSD", "Oil/Silver"),
]

def analyze_portfolio_frequency():
    print("--- PORTFOLIO FREQUENCY ANALYSIS (2025) ---")

    total_trades = 0
    pair_counts = {}

    for y_sym, x_sym, label in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")

        try:
            df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
            df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

            df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

            # 2025 Only
            start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
            sub = df.filter(pl.col("timestamp") >= start_dt)
            if len(sub) == 0: continue

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

            trades = 0
            in_pos = 0

            for i in range(500, len(y)):
                window = errors[i-500:i]
                mu, std = np.mean(window), np.std(window)
                if std < 1e-6: continue
                z = (errors[i] - mu) / std

                if in_pos == 0:
                    if z > 1.5: in_pos = -1
                    elif z < -1.5: in_pos = 1
                elif in_pos == 1:
                    if z > 0.0 or z < -2.0: in_pos = 0; trades += 1
                elif in_pos == -1:
                    if z < 0.0 or z > 2.0: in_pos = 0; trades += 1

            pair_counts[label] = trades
            total_trades += trades

        except Exception as e:
            print(f"Error {label}: {e}")

    print(f"| Pair | Trades (2025) |")
    print("|---|---|")
    for label, count in pair_counts.items():
        print(f"| {label} | {count} |")

    print("-" * 30)
    print(f"Total Portfolio Trades: {total_trades}")
    print(f"Avg Trades Per Month:   {total_trades / 12:.1f}")
    print(f"Avg Trades Per Week:    {total_trades / 52:.1f}")

if __name__ == "__main__":
    analyze_portfolio_frequency()
