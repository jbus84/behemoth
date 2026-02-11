
import polars as pl
import numpy as np
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_1h"
Y_SYM = "BCOUSD"
X_SYM = "GRXEUR"
COST_BPS = 9.0

def run_bias_check():
    print(f"--- BIAS CHECK: {Y_SYM}/{X_SYM} (H1) ---")

    # Load
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{Y_SYM}_1h.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{X_SYM}_1h.parquet"))
    except: return

    df = df_y.rename({f"close_{Y_SYM}": "Y"}).join(
        df_x.rename({f"close_{X_SYM}": "X"}), on="timestamp", how="inner"
    ).sort("timestamp")

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())

    # Run Two Filters Parallel
    kf_post = KalmanFilterReg(Q=1e-5, R=1e-3)
    kf_pre = KalmanFilterReg(Q=1e-5, R=1e-3)

    post_errors = []
    pre_errors = []

    for i in range(len(y)):
        # POST-FIT (Biased)
        b_post, _ = kf_post.update(x[i], y[i])
        post_errors.append(y[i] - b_post * x[i])

        # PRE-FIT (Real-Time)
        # Note: update() returns (beta_new, residual_pre_fit)
        # We must confirm this in the class code.
        # Yes: residual = y - beta_old * x.
        b_new, err_pre = kf_pre.update(x[i], y[i])
        pre_errors.append(err_pre)

    # Backtest Function
    def backtest(errors, label):
        trades = []
        in_pos = 0
        entry_val = 0.0

        for i in range(500, len(errors)):
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
                    trades.append(-COST_BPS)
                elif z < -2.0:
                    in_pos = 1
                    entry_val = spread
                    trades.append(-COST_BPS)
            elif in_pos == 1:
                if z > 0.0 or z < -4.0:
                    trades.append((spread - entry_val)*10000 - COST_BPS)
                    in_pos = 0
            elif in_pos == -1:
                if z < 0.0 or z > 4.0:
                    trades.append((entry_val - spread)*10000 - COST_BPS)
                    in_pos = 0

        total_pnl = np.sum(trades)
        n_trades = len(trades) / 2 # Approx
        avg_trade = total_pnl / n_trades if n_trades > 0 else 0
        print(f"[{label}] Total PnL: {total_pnl:.0f} bps | Avg Trade: {avg_trade:.2f} bps | Trades: {n_trades:.0f}")
        return avg_trade

    # Compare
    print(f"\n--- STATS ANALYSIS ---")
    std_post = np.std(post_errors)
    std_pre = np.std(pre_errors)
    print(f"Post-Fit Std Dev: {std_post:.6f} (The 'Cleaned' Noise)")
    print(f"Pre-Fit Std Dev:  {std_pre:.6f} (The 'Raw' Shock)")
    print(f"Ratio (Pre/Post): {std_pre/std_post:.2f}x")

    print(f"\n--- PnL ANALYSIS ---")
    p1 = backtest(post_errors, "POST-FIT (Biased)")
    p2 = backtest(pre_errors,  "PRE-FIT  (Real)  ")

    print(f"\n--- EXPLANATION ---")
    if p2 > p1:
        print("Why the Jump? The Kalman Filter 'absorbs' part of the shock in the Post-Fit residual.")
        print("In Real-Time, you trade the FULL shock (Pre-Fit).")
        print("In Backtest (Post-Fit), you only trade what's 'left over' after the filter adapts.")
        print(f"You essentially capture {(p2/p1 - 1)*100:.0f}% more alpha by trading before the filter updates.")

    diff = p1 - p2
    print(f"\nBias Impact: {diff:.2f} bps per trade.")

    if p2 > 0:
        print("VERDICT: PASS. Strategy works without lookahead.")
    else:
        print("VERDICT: FAIL. Strategy dependent on lookahead.")

if __name__ == "__main__":
    run_bias_check()
