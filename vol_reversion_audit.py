import polars as pl
import numpy as np
import os

def run_vol_reversion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> VOLATILITY MEAN REVERSION AUDIT FOR {dataset_path} <<<")
    
    # 1. Rolling Volatility Z-Score (Lookback: 60m)
    df = df.with_columns([
        pl.col("NSXUSD_vol_30m").rolling_mean(window_size=60).alias("v_mean"),
        pl.col("NSXUSD_vol_30m").rolling_std(window_size=60).alias("v_std")
    ])
    
    df = df.with_columns(
        ((pl.col("NSXUSD_vol_30m") - pl.col("v_mean")) / pl.col("v_std")).alias("v_z")
    )
    
    # 2. Strategy: Fade the Vol Spike
    # If Vol Z > 3.0: Fade the direction of the 1m move.
    
    print(f"{'Vol Z Thr':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    for z_thr in [2.5, 3.0, 3.5, 4.0]:
        # Logic: Extreme Vol AND 1m Move exists. Fade the 1m move.
        df_thr = df.with_columns(
            (pl.when((pl.col("v_z") > z_thr) & (pl.col("NSXUSD_ret_1m") > 0)).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when((pl.col("v_z") > z_thr) & (pl.col("NSXUSD_ret_1m") < 0)).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{z_thr:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_vol_reversion_audit(f"graph_dataset_1m_{y}.parquet")
