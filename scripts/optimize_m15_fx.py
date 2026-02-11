
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

FX_PAIRS = [
    ("USDCHF", "AUDUSD", "Swiss/Aussie"),
    ("EURUSD", "EURJPY", "Euro/Yen"),
    ("GBPUSD", "USDCAD", "Cable/Loonie"),
]

def optimize_m15_fx():
    print("--- M15 FX OPTIMIZATION (2025) ---")

    for y_sym, x_sym, label in FX_PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_15m.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_15m.parquet")

        if not os.path.exists(p_y) or not os.path.exists(p_x): continue

        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

        # 2025 Only
        start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        sub = df.filter(pl.col("timestamp") >= start_dt)

        y = np.log(sub["Y"].to_numpy())
        x = np.log(sub["X"].to_numpy())

        # Kalman
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []

        for i in range(len(y)):
            if i < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
            b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
            betas.append(b)
            errors.append((y[i]-mu_y) - b*(x[i]-mu_x))

        print(f"\n[{label}]")
        print("| Threshold | Net PnL (bps) | Trades | Win Rate |")
        print("|---|---|---|---|")

        for thresh in [2.0, 2.5, 3.0, 3.5]:
            in_pos = 0
            pnl_total = 0.0
            trades = 0
            wins = 0
            entry_y, entry_x, entry_beta = 0., 0., 0.
            cost_bps = 9.0
            stop_level = max(3.5, thresh + 1.0)

            for i in range(500, len(y)):
                window = errors[i-500:i]
                mu, std = np.mean(window), np.std(window)
                if std < 1e-6: continue
                z = (errors[i] - mu) / std

                pnl = 0.0
                if in_pos == 0:
                    if z > thresh: in_pos = -1; entry_beta=betas[i-1]; entry_y=y[i]; entry_x=x[i]
                    elif z < -thresh: in_pos = 1; entry_beta=betas[i-1]; entry_y=y[i]; entry_x=x[i]
                elif in_pos == 1:
                    if z > 0.0:
                        gross = (y[i]-entry_y) - entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades += 1; wins += 1
                    elif z < -stop_level:
                        gross = (y[i]-entry_y) - entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades += 1
                elif in_pos == -1:
                    if z < 0.0:
                        gross = -(y[i]-entry_y) + entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades += 1; wins += 1
                    elif z > stop_level:
                        gross = -(y[i]-entry_y) + entry_beta*(x[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        in_pos = 0; trades += 1

                pnl_total += pnl

            wr = wins/trades*100 if trades > 0 else 0
            print(f"| {thresh} | {pnl_total:.1f} | {trades} | {wr:.1f}% |")

if __name__ == "__main__":
    optimize_m15_fx()
