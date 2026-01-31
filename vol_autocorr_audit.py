import polars as pl
import numpy as np
import os
from scipy.stats import spearmanr

def run_vol_autocorr():
    print(">>> VOLATILITY-DEPENDENT AUTOCORRELATION AUDIT <<<")
    
    repo = "/Users/danielfisher/repositories/behemoth"
    years = ["2023", "2024"]
    
    # 1. Load Nasdaq
    dfs = []
    for y in years:
        f = os.path.join(repo, f"graph_dataset_1m_{y}.parquet")
        if os.path.exists(f):
            dfs.append(pl.read_parquet(f))
    
    if not dfs:
        print("No Data.")
        return

    df_raw = pl.concat(dfs).sort("timestamp")
    if "NSXUSD_mid" in df_raw.columns: df_raw = df_raw.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
    elif "close" in df_raw.columns: df_raw = df_raw.with_columns(pl.col("close").alias("NSXUSD"))
    
    timeframes = ["1m", "5m", "15m", "1h"]
    
    for tf in timeframes:
        print(f"\n=== TIMEFRAME: {tf} ===")
        
        # Resample
        d = df_raw.group_by_dynamic("timestamp", every=tf, closed="right", label="right").agg([
            pl.col("NSXUSD").last().alias("price")
        ]).sort("timestamp")
        
        # Features
        d = d.with_columns(
            ((pl.col("price") / pl.col("price").shift(1) - 1) * 10000).alias("ret"),
        )
        d = d.with_columns(
            pl.col("ret").rolling_std(12).alias("vol"),
            ((pl.col("price").shift(-1) / pl.col("price") - 1) * 10000).alias("ret_next")
        ).drop_nulls()
        
        # Define Medium Vol Regime
        vol = d["vol"].to_numpy()
        q1 = np.percentile(vol, 25)
        q3 = np.percentile(vol, 75)
        
        d_med = d.filter((pl.col("vol") > q1) & (pl.col("vol") <= q3))
        
        print(f"  Medium Volatility Regime ({q1:.4f} - {q3:.4f} bps) - Count: {len(d_med)}")
        
        # Calculate Lags 1-5 Correlation
        for lag in range(1, 6):
            d_lag = d.with_columns(
                ((pl.col("price").shift(-1) / pl.col("price") - 1) * 10000).alias("target_next"),
                ((pl.col("price") / pl.col("price").shift(1) - 1) * 10000).alias(f"ret_lag_0"), 
                ((pl.col("price").shift(1) / pl.col("price").shift(2) - 1) * 10000).alias(f"ret_lag_1"),
                ((pl.col("price").shift(2) / pl.col("price").shift(3) - 1) * 10000).alias(f"ret_lag_2"),
                ((pl.col("price").shift(3) / pl.col("price").shift(4) - 1) * 10000).alias(f"ret_lag_3"),
                ((pl.col("price").shift(4) / pl.col("price").shift(5) - 1) * 10000).alias(f"ret_lag_4"),
            ).drop_nulls()
            
            # Filter for Medium Vol
            d_lag_med = d_lag.filter((pl.col("vol") > q1) & (pl.col("vol") <= q3))
            
            print("  --- Lagged Correlations (Predicting Next Return) ---")
            for k in range(5):
                 feat = f"ret_lag_{k}"
                 c, p = spearmanr(d_lag_med[feat].to_numpy(), d_lag_med["target_next"].to_numpy())
                 print(f"    Lag {k+1} (t-{k}): IC = {c:.4f} (p={p:.3f})")
            
            print("  --- Internal Structure (Chop Persistence) ---")
            c1, _ = spearmanr(d_lag_med["ret_lag_0"].to_numpy(), d_lag_med["ret_lag_1"].to_numpy())
            print(f"    Ret(t) vs Ret(t-1): {c1:.4f}")
            c2, _ = spearmanr(d_lag_med["ret_lag_1"].to_numpy(), d_lag_med["ret_lag_2"].to_numpy())
            print(f"    Ret(t-1) vs Ret(t-2): {c2:.4f}")
            
            break 

if __name__ == "__main__":
    run_vol_autocorr()
