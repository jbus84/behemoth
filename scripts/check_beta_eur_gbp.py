
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

def check_beta():
    print("--- CHECKING BETA: EUR vs GBP (M15) ---")
    p_eur = os.path.join(DATA_DIR, "EURUSD_15m.parquet")
    p_gbp = os.path.join(DATA_DIR, "GBPUSD_15m.parquet")
    
    df_eur = pl.read_parquet(p_eur).rename({"close_EURUSD": "X"})
    df_gbp = pl.read_parquet(p_gbp).rename({"close_GBPUSD": "Y"})
    
    df = df_eur.join(df_gbp, on="timestamp", how="inner").sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year() == 2025)
    
    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    
    for i in range(len(y)):
        if i < 10: mu_y, mu_x = y[i], x[i]
        else: mu_y, mu_x = np.mean(y[max(0,i-500):i]), np.mean(x[max(0,i-500):i])
        b, _ = kf.update(x[i]-mu_x, y[i]-mu_y)
        betas.append(b)
        
    avg_beta = np.mean(betas)
    
    # Returns Analysis (Volatility)
    y_ret = np.diff(y)
    x_ret = np.diff(x)
    
    # OLS on Returns
    # y_ret = beta * x_ret
    beta_ret = np.cov(x_ret, y_ret)[0,1] / np.var(x_ret)
    
    # Volatility Ratio
    vol_y = np.std(y_ret)
    vol_x = np.std(x_ret)
    vol_ratio = vol_y / vol_x
    
    print(f"Kalman Beta (Prices):   {avg_beta:.4f} (Cointegration Slope)")
    print(f"Returns Beta (OLS):     {beta_ret:.4f} (Correlation * VolRatio)")
    print(f"Volatility Ratio (Y/X): {vol_ratio:.4f} (True Movements)")
    
    if vol_ratio > 1:
        print(f"VERDICT: GBP is {vol_ratio:.2f}x more volatile than EUR.")
    else:
        print(f"VERDICT: EUR is {1/vol_ratio:.2f}x more volatile than GBP.")

if __name__ == "__main__":
    check_beta()
