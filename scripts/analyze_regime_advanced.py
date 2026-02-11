
import polars as pl
import numpy as np
import os
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil (Winner)"),
    ("USDCHF", "GRXEUR", "CHF/DAX (Loser)"),
]

def calculate_half_life(ts):
    """Calculate Half-Life of Mean Reversion via OLS (Ornstein-Uhlenbeck)"""
    lag = np.roll(ts, 1)
    lag[0] = 0
    ret = ts - lag
    lag = lag[1:]
    ret = ret[1:]

    # Regress diff against lag
    # dS = theta * (mu - S) * dt
    # ret = lambda * lag + C
    if len(lag) < 10: return 0

    model = sm.OLS(ret, sm.add_constant(lag))
    res = model.fit()
    lam = res.params[1]

    if lam >= 0: return 1000 # Non-mean reverting
    return -np.log(2) / lam

def analyze_advanced():
    print("--- DYNAMIC REGIME DETECTION: ADVANCED METRICS (2024) ---")
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

            # 1. Rolling Correlation (Window 50)
            corrs = []
            for i in range(50, len(y)):
                win_y = y[i-50:i]
                win_x = x[i-50:i]
                corrs.append(np.corrcoef(win_x, win_y)[0,1])

            avg_corr = np.mean(corrs)

            # 2. Rolling ADF & Half-Life on Kalman Residuals (Window 100)
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            residuals = []
            y_win, x_win = [], []

            for i in range(len(y)):
                y_win.append(y[i]); x_win.append(x[i])
                if len(y_win)>500: y_win.pop(0); x_win.pop(0)
                if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
                else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)

                b, res = kf.update(x[i]-mu_x, y[i]-mu_y)
                residuals.append(res)

            adfs = []
            halflives = []
            res_arr = np.array(residuals)

            for i in range(100, len(res_arr), 10): # Step 10 for speed
                window = res_arr[i-100:i]

                # ADF
                try:
                    adf_res = adfuller(window, autolag='AIC')
                    adfs.append(adf_res[1]) # p-value
                except:
                    adfs.append(1.0)

                # Half Life
                try:
                    hl = calculate_half_life(window)
                    halflives.append(hl)
                except:
                    halflives.append(1000)

            avg_adf_p = np.mean(adfs)
            pct_stat = np.mean(np.array(adfs) < 0.05) * 100

            avg_hl = np.mean(halflives)

            print(f"[{label}]")
            print(f"  Avg Correlation: {avg_corr:.4f}")
            print(f"  Avg ADF P-Value: {avg_adf_p:.4f}")
            print(f"  % Stationary:    {pct_stat:.1f}%")
            print(f"  Avg Half-Life:   {avg_hl:.1f} bars")
            print("-" * 30)

        except Exception as e:
            print(f"Error {label}: {e}")

if __name__ == "__main__":
    analyze_advanced()
