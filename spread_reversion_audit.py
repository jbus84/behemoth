import polars as pl
import numpy as np
import os

def run_spread_reversion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> INDEX SPREAD REVERSION AUDIT FOR {dataset_path} <<<")
    
    # 1. Calculate Ratio/Spread
    # We use log prices to make the relationship linear
    df = df.with_columns([
        (pl.col("NSXUSD_mid").log() - pl.col("SPXUSD_mid").log()).alias("nsx_spx_log_ratio")
    ])
    
    # 2. Rolling Z-Score of the Ratio (Lookback: 60m)
    df = df.with_columns([
        pl.col("nsx_spx_log_ratio").rolling_mean(window_size=60).alias("ratio_mean"),
        pl.col("nsx_spx_log_ratio").rolling_std(window_size=60).alias("ratio_std")
    ])
    
    df = df.with_columns(
        ((pl.col("nsx_spx_log_ratio") - pl.col("ratio_mean")) / pl.col("ratio_std")).alias("ratio_z")
    )
    
    # 3. Strategy: Convergence Trade
    # If Z > 2.0: Short NSX, Long SPX (Bet on ratio coming down)
    # If Z < -2.0: Long NSX, Short SPX (Bet on ratio coming up)
    # Target: 15m later. 
    # Spread cost: 1.5 bps for NSX + 1.5 bps for SPX = 3.0 bps total cost per trade.
    
    COST = 3.0
    
    print(f"{'Z-Threshold':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    for z_thr in [1.5, 2.0, 2.5]:
        df_thr = df.with_columns([
            (pl.col("ratio_z") > z_thr).alias("signal_short_nsx"),
            (pl.col("ratio_z") < -z_thr).alias("signal_long_nsx")
        ])
        
        # PnL = (NSX_ret - SPX_ret) for Long NSX trade
        # PnL = (SPX_ret - NSX_ret) for Short NSX trade
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("signal_long_nsx"))
              .then((pl.col("target_nsx_15m") - pl.col("target_spx_15m")) * 10000 - COST)
              .when(pl.col("signal_short_nsx"))
              .then((pl.col("target_spx_15m") - pl.col("target_nsx_15m")) * 10000 - COST)
              .otherwise(0)).alias("pnl")
        )
        
        results = df_thr.filter(pl.col("pnl") != 0)
        if len(results) > 0:
            print(f"{z_thr:<12} | {len(results):<8} | { (results['pnl'] > 0).mean()*100:>8.2f}% | {results['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_spread_reversion_audit(f"graph_dataset_1m_{y}.parquet")
