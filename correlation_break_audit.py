import polars as pl
import numpy as np
import os

def run_correlation_break_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> CORRELATION-BREAK REVERSION AUDIT FOR {dataset_path} <<<")
    
    # We want to find the asset that is "fighting" the most.
    # We align all returns to "USD Strength" direction for consistency.
    def align_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'NSXUSD', 'SPXUSD']:
             return -pl.col(f"{pair}_ret_1m") # Negative ret = USD Strength
        else:
             return pl.col(f"{pair}_ret_1m")  # Positive ret = USD Strength

    df = df.with_columns([
        align_ret(n, df).alias(f"{n}_aligned") for n in nodes
    ])
    
    # 1. Global Macro Trend (Mean Aligned Return)
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{n}_aligned") for n in nodes]).alias("global_macro_trend")
    )
    
    # 2. Rogue Detection (Distance from Mean)
    # We'll focus on the Nasdaq as the potential laggard/rogue
    df = df.with_columns(
        (pl.col("NSXUSD_aligned") - pl.col("global_macro_trend")).alias("nsx_rogue_distance")
    )
    
    print(f"{'Rogue Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    # Strategy: If NSX is a Rogue (Distance > Thr), it implies it is "Behind" or "Fighting" the trend.
    # Trade for CONVERGENCE (Beta-neutral style, but we just want the NSX leg).
    # If Rogue Distance > 0 (NSX is TOO STRENGTH relative to others), it must FALL to align.
    # If Rogue Distance < 0 (NSX is TOO WEAK relative to others), it must RISE to align.
    
    for thr_bps in [1.0, 2.0, 3.0, 5.0]:
        t = thr_bps / 10000
        
        df_thr = df.with_columns([
            (pl.col("nsx_rogue_distance") > t).alias("too_strong"), # SHORT NSX
            (pl.col("nsx_rogue_distance") < -t).alias("too_weak")    # LONG NSX
        ])
        
        # PnL (15m horizon)
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("too_weak")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("too_strong")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_correlation_break_audit(f"graph_dataset_1m_{y}.parquet")
