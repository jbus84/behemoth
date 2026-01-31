import polars as pl
import numpy as np
import os

def run_long_stat_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> LONG-HORIZON STAT-ARB AUDIT (120m) FOR {dataset_path} <<<")
    
    # 1. Ratio Stats (240m rolling window for smoother Z)
    df = df.with_columns([
        (pl.col("NSXUSD_mid").log() - pl.col("SPXUSD_mid").log()).alias("ratio")
    ])
    
    df = df.with_columns([
        pl.col("ratio").rolling_mean(window_size=240).alias("r_mean"),
        pl.col("ratio").rolling_std(window_size=240).alias("r_std")
    ])
    
    df = df.with_columns(
        ((pl.col("ratio") - pl.col("r_mean")) / pl.col("r_std")).alias("r_z")
    )
    
    # 2. Target: Next 120m NSX Return Relative to SPX
    df = df.with_columns(
        ((pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()) - 
         (pl.col("SPXUSD_mid").shift(-120).log() - pl.col("SPXUSD_mid").log())).alias("target_relative_120m")
    )
    
    print(f"{'Z-Threshold':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    # Cost: 1.5 bps for NSX + 1.5 bps for SPX = 3.0 bps total.
    COST = 3.0
    
    for z_thr in [2.0, 2.5, 3.0]:
        df_thr = df.with_columns([
            (pl.col("r_z") > z_thr).alias("si_short"), # Short NSX, Long SPX
            (pl.col("r_z") < -z_thr).alias("si_long")  # Long NSX, Short SPX
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("si_long")).then(pl.col("target_relative_120m") * 10000 - COST)
              .when(pl.col("si_short")).then(-pl.col("target_relative_120m") * 10000 - COST)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{z_thr:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_long_stat_audit(f"graph_dataset_1m_{y}.parquet")
