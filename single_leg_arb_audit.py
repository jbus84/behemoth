import polars as pl
import numpy as np
import os

def run_single_leg_arb_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> SINGLE-LEG INDEX ARB AUDIT FOR {dataset_path} <<<")
    
    # 1. Ratio Stats (60m rolling)
    df = df.with_columns([
        (pl.col("NSXUSD_mid").log() - pl.col("SPXUSD_mid").log()).alias("ratio")
    ])
    
    df = df.with_columns([
        pl.col("ratio").rolling_mean(window_size=60).alias("r_mean"),
        pl.col("ratio").rolling_std(window_size=60).alias("r_std")
    ])
    
    df = df.with_columns(
        ((pl.col("ratio") - pl.col("r_mean")) / pl.col("r_std")).alias("r_z")
    )
    
    print(f"{'Z-Threshold':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    # Strategy: If NSX is too high (Z > Thr), Short NSX.
    # If NSX is too low (Z < -Thr), Long NSX.
    # Horizon: 15m.
    
    for z_thr in [1.5, 2.0, 2.5, 3.0]:
        df_thr = df.with_columns([
            (pl.col("r_z") > z_thr).alias("si_short"),
            (pl.col("r_z") < -z_thr).alias("si_long")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("si_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("si_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{z_thr:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_single_leg_arb_audit(f"graph_dataset_1m_{y}.parquet")
