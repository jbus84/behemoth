import polars as pl
import numpy as np
import os

def run_vol_expansion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> VOLATILITY EXPANSION AUDIT FOR {dataset_path} <<<")
    
    # 1. Rolling Volatility Stats
    df = df.with_columns([
        pl.col("NSXUSD_vol_30m").rolling_mean(window_size=360).alias("v_background") # 6h avg vol
    ])
    
    # 2. Strategy: Compressed Breakout
    # Logic: Vol < 0.5 * Background (Compression)
    # AND 1m Move > 2.0 bps (The Break!)
    # Trade direction of the break. Target: 15m later.
    
    df = df.with_columns(
        (pl.col("NSXUSD_vol_30m") < 0.7 * pl.col("v_background")).alias("compressed")
    )
    
    print(f"{'Break Thr':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    for thr in [1.5, 2.0, 3.0]:
        t = thr / 10000
        
        df_thr = df.with_columns([
            (pl.col("compressed") & (pl.col("NSXUSD_ret_1m") > t)).alias("break_up"),
            (pl.col("compressed") & (pl.col("NSXUSD_ret_1m") < -t)).alias("break_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("break_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("break_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_vol_expansion_audit(f"graph_dataset_1m_{y}.parquet")
