import polars as pl
import numpy as np
import os
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_hourly_audit():
    print(">>> HOURLY MACRO AUDIT <<<")
    
    repo = "/Users/danielfisher/repositories/behemoth"
    
    # Load 1m Data
    f_nsx = os.path.join(repo, "graph_dataset_1m_2023.parquet")
    f_dax = os.path.join(repo, "dax_dataset_1m_2023.parquet") # Assuming we have this?
    # If not, we rely on what we have. 
    # Check if DAX exists, else skip cross-asset part.
    
    has_dax = os.path.exists(f_dax)
    
    dfs_nsx = []
    if os.path.exists(f_nsx): dfs_nsx.append(pl.read_parquet(f_nsx))
    
    if not dfs_nsx:
        print("No Data Failure")
        return

    df = pl.concat(dfs_nsx)
    if "NSXUSD_mid" in df.columns: df = df.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
    elif "close" in df.columns: df = df.with_columns(pl.col("close").alias("NSXUSD"))
    
    # Resample to 1H
    print("Resampling to Hourly...")
    df_1h = df.sort("timestamp").group_by_dynamic("timestamp", every="1h", closed="right", label="right").agg([
        pl.col("NSXUSD").last().alias("close"),
        pl.col("NSXUSD").first().alias("open"),
        pl.col("NSXUSD").max().alias("high"),
        pl.col("NSXUSD").min().alias("low")
    ])
    
    # Add DAX if available
    if has_dax:
        dax = pl.read_parquet(f_dax)
        if "GRXEUR_mid" in dax.columns: dax = dax.with_columns(pl.col("GRXEUR_mid").alias("GRXEUR"))
        elif "close" in dax.columns: dax = dax.with_columns(pl.col("close").alias("GRXEUR"))
        
        dax_1h = dax.sort("timestamp").group_by_dynamic("timestamp", every="1h", closed="right", label="right").agg([
            pl.col("GRXEUR").last().alias("dax_close")
        ])
        
        df_1h = df_1h.join(dax_1h, on="timestamp", how="left").sort("timestamp")
    
    # Features (Hourly)
    print("Calculating Hourly Features...")
    df_1h = df_1h.with_columns(
        ((pl.col("close") / pl.col("close").shift(1) - 1) * 10000).alias("ret_1h")
    )
    
    def calc_rsi(expr, n=14):
        delta = expr.diff()
        u = delta.clip(lower_bound=0)
        d = delta.clip(upper_bound=0).abs()
        rs = u.rolling_mean(n) / (d.rolling_mean(n) + 1e-9)
        return 100 - (100 / (1 + rs))
        
    df_1h = df_1h.with_columns([
        calc_rsi(pl.col("close"), 14).alias("rsi_14"),
        (pl.col("close") / pl.col("close").shift(4) - 1).alias("roc_4h"),
        pl.col("ret_1h").rolling_std(4).alias("vol_4h"),
        # Target: Next Hour Return
        ((pl.col("close").shift(-1) / pl.col("close") - 1) * 10000).alias("target_next_1h")
    ])
    
    if has_dax:
        df_1h = df_1h.with_columns(
            (pl.col("dax_close") / pl.col("dax_close").shift(1) - 1).alias("dax_ret_1h")
        )

    df_1h = df_1h.drop_nulls()
    
    # Analysis
    print(f"\nSample Size (Hourly): {len(df_1h)}")
    
    feats = ["rsi_14", "roc_4h", "vol_4h"]
    if has_dax: feats.append("dax_ret_1h")
    
    print("\n--- HOURLY IC SCORES ---")
    
    # Spearman
    for f in feats:
        c, _ = spearmanr(df_1h[f].to_numpy(), df_1h["target_next_1h"].to_numpy())
        print(f"{f:<15}: {c:.4f}")
        
    # Validation: RSI Reversion?
    # Strategy: Buy if RSI < 30, Sell if RSI > 70
    oversold = df_1h.filter(pl.col("rsi_14") < 30)
    overbought = df_1h.filter(pl.col("rsi_14") > 70)
    
    # Mean Reversion Logic
    reversion_pnl_os = np.mean(oversold["target_next_1h"]) # Expect Positive
    reversion_pnl_ob = np.mean(overbought["target_next_1h"]) # Expect Negative
    
    print("\n--- RSI MEAN REVERSION CHECK ---")
    print(f"RSI < 30 (Oversold) Next Hour Return: {reversion_pnl_os:.2f} bps  (Count: {len(oversold)})")
    print(f"RSI > 70 (Overbought) Next Hour Return: {reversion_pnl_ob:.2f} bps (Count: {len(overbought)})")
    
    net_rev = reversion_pnl_os - reversion_pnl_ob
    print(f"Net Reversion Spread: {net_rev:.2f} bps")
    print("If > 5 bps, we have a signal.")

if __name__ == "__main__":
    run_hourly_audit()
