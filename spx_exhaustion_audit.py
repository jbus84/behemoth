import polars as pl
import numpy as np
import os

def run_spx_exhaustion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> SPX MOMENTUM EXHAUSTION AUDIT FOR {dataset_path} <<<")
    
    # 1. SPX Momentum Intensity (1m)
    df = df.with_columns([
        pl.col("SPXUSD_ret_1m").alias("shock")
    ])
    
    # 2. Strategy: Fade the Shock if it hits tail energy
    # We use Q99 of the day for SPX shocks
    df = df.with_columns([
        pl.col("shock").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("shock_thr")
    ])
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: IF SPX shock > Q99: Fade Nasdaq.
    df_strat = df.with_columns([
        (pl.when((pl.col("shock") > pl.col("shock_thr"))).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .when((pl.col("shock") < -pl.col("shock_thr"))).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    ])
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"SPX Q99 Fade         | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_spx_exhaustion_audit(f"graph_dataset_1m_{y}.parquet")
