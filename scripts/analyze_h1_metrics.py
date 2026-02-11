
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"
Y_SYM = "BCOUSD"
X_SYM = "GRXEUR"
SPREAD_COST_BPS = 9.0  # Bid/Ask Spread (Measured)
SLIPPAGE_BPS = 1.0     # Execution Slippage (Estimated)
TOTAL_COST_BPS = SPREAD_COST_BPS + SLIPPAGE_BPS

def analyze_metrics():
    print(f"--- DETAILED METRICS REPORT ({Y_SYM}/{X_SYM}) ---")
    print(f"Cost Assumption: {TOTAL_COST_BPS} bps (Spread + Slippage)")

    # Load
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_1h.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_1h.parquet"))
    except:
        print("Data missing.")
        return

    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).sort("timestamp")

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())

    # Generate Spreads
    errors = []
    for i in range(len(y)):
        b, _ = kf.update(x[i], y[i])
        errors.append(y[i] - b * x[i])

    # Simulate Trades
    trades = []
    in_pos = 0
    entry_val = 0.0

    for i in range(500, len(y)):
        window = errors[i-500:i]
        mu = np.mean(window)
        std = np.std(window)
        if std < 1e-6: continue

        z = (errors[i] - mu) / std
        spread = errors[i]

        if in_pos == 0:
            if z > 2.0:
                in_pos = -1
                entry_val = spread
            elif z < -2.0:
                in_pos = 1
                entry_val = spread
        elif in_pos == 1:
            if z > 0.0 or z < -4.0:
                gross_pnl = spread - entry_val
                # Convert log diff to bps
                bps = gross_pnl * 10000
                trades.append(bps)
                in_pos = 0
        elif in_pos == -1:
            if z < 0.0 or z > 4.0:
                gross_pnl = entry_val - spread
                bps = gross_pnl * 10000
                trades.append(bps)
                in_pos = 0

    # Analysis
    trades = np.array(trades)
    net_trades = trades - TOTAL_COST_BPS

    n_trades = len(net_trades)
    winners = net_trades[net_trades > 0]
    losers = net_trades[net_trades <= 0]

    win_rate = len(winners) / n_trades * 100
    avg_win = np.mean(winners)
    avg_loss = np.mean(losers)
    exp_val = np.mean(net_trades)

    print("\n--- PERFORMANCE MATRIX (Per Trade) ---")
    print(f"Win Rate:       {win_rate:.2f}%")
    print(f"Avg Win:        {avg_win:.2f} bps")
    print(f"Avg Loss:       {avg_loss:.2f} bps")
    print(f"Expected Value: {exp_val:.2f} bps")
    print(f"Typical Spread: {SPREAD_COST_BPS:.2f} bps")
    print(f"Slippage Est:   {SLIPPAGE_BPS:.2f} bps")
    print(f"Total Cost:     {TOTAL_COST_BPS:.2f} bps")
    print(f"Sample Size:    {n_trades} trades")

if __name__ == "__main__":
    analyze_metrics()
