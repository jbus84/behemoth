import polars as pl
import numpy as np
import os

def run_micro_trend_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> MICRO-TREND PERSISTENCE AUDIT FOR {dataset_path} <<<")
    
    # 1. Detect 3 consecutive 1m bars in same direction
    df = df.with_columns([
        pl.col("NSXUSD_ret_1m").alias("r1"),
        pl.col("NSXUSD_ret_1m").shift(1).alias("r2"),
        pl.col("NSXUSD_ret_1m").shift(2).alias("r3")
    ])
    
    print(f"{'Intensity (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for i_bps in [0.5, 1.0, 1.5, 2.0]:
        t = i_bps / 10000
        
        # Signal: all 3 bars > t OR all 3 bars < -t
        df_thr = df.with_columns([
            ((pl.col("r1") > t) & (pl.col("r2") > t) & (pl.col("r3") > t)).alias("trend_up"),
            ((pl.col("r1") < -t) & (pl.col("r2") < -t) & (pl.col("r3") < -t)).alias("trend_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("trend_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("trend_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{i_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_micro_trend_audit(f"graph_dataset_1m_{y}.parquet")
