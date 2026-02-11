
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def backtest_eur_shadow():
    print("--- EUR SHADOW TRADE (STABLE LEG M15) ---")
    print("Strategy: Calculate Signal from EUR/GBP. Trade ONLY EUR.")

    # Load Data
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")

    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"}) # Predictor (Stable)
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"}) # Target (Volatile)

    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")

    y_full = np.log(df["Y"].to_numpy()) # GBP
    x_full = np.log(df["X"].to_numpy()) # EUR
    ts_full = df["timestamp"].to_numpy() # Timestamps

    # Kalman Filter
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []

    for i in range(len(y_full)):
        if i < 10: mu_y, mu_x = y_full[i], x_full[i]
        else: mu_y, mu_x = np.mean(y_full[max(0,i-500):i]), np.mean(x_full[max(0,i-500):i])
        b, _ = kf.update(x_full[i]-mu_x, y_full[i]-mu_y)
        betas.append(b)
        errors.append((y_full[i]-mu_y) - b*(x_full[i]-mu_x))

    print(f"\n--- EUR MEAN REVERSION AUDIT (STABLE LEG) [Z=2.0] ---")
    print("| Year | Net PnL (bps) | Trades | Win Rate |")
    print("|---|---|---|---|")

    thresh = 2.0
    stop_level = 3.5
    COST_BPS = 1.0

    total_pnl = 0.0
    current_year = -1
    year_pnl = 0.0
    year_trades = 0
    year_wins = 0

    in_pos = 0
    entry_price = 0.0

    for i in range(500, len(y_full)):
        ts_i = ts_full[i]
        yr = ts_i.astype('datetime64[Y]').astype(int) + 1970

        if yr != current_year:
            if current_year != -1:
                wr = year_wins/year_trades*100 if year_trades > 0 else 0
                print(f"| {current_year} | {year_pnl:.1f} | {year_trades} | {wr:.1f}% |")
                total_pnl += year_pnl
            current_year = yr
            year_pnl = 0.0
            year_trades = 0
            year_wins = 0

        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std

        pnl = 0.0

        if in_pos == 0:
            if z > thresh:
                # Z High: GBP High / EUR Low.
                # Standard Mean Reversion: BUY EUR.
                in_pos = 1; entry_price = x_full[i]
            elif z < -thresh:
                # Z Low: GBP Low / EUR High.
                # Standard Mean Reversion: SELL EUR.
                in_pos = -1; entry_price = x_full[i]

        elif in_pos == 1: # Long EUR
            if z < 0.0: # Reverted
                gross = x_full[i] - entry_price
                pnl = gross * 10000 - COST_BPS
                in_pos = 0; year_trades += 1
                if pnl > 0: year_wins += 1
            elif z > stop_level: # Stop
                gross = x_full[i] - entry_price
                pnl = gross * 10000 - COST_BPS
                in_pos = 0; year_trades += 1
                if pnl > 0: year_wins += 1

        elif in_pos == -1: # Short EUR
            if z > 0.0: # Reverted
                gross = -(x_full[i] - entry_price)
                pnl = gross * 10000 - COST_BPS
                in_pos = 0; year_trades += 1
                if pnl > 0: year_wins += 1
            elif z < -stop_level: # Stop
                gross = -(x_full[i] - entry_price)
                pnl = gross * 10000 - COST_BPS
                in_pos = 0; year_trades += 1
                if pnl > 0: year_wins += 1

        year_pnl += pnl

    if current_year != -1:
        wr = year_wins/year_trades*100 if year_trades > 0 else 0
        print(f"| {current_year} | {year_pnl:.1f} | {year_trades} | {wr:.1f}% |")
        total_pnl += year_pnl

    print(f"| **TOTAL** | **{total_pnl:.0f}** | | |")

if __name__ == "__main__":
    backtest_eur_shadow()
