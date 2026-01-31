import polars as pl
import numpy as np
import os

def run_collective_force_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Aligned Individual Returns
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    # 2. Individual Tail Thresholds (85th percentile for higher frequency)
    df = df.with_columns([
        pl.col(f"{a}_usd").abs().rolling_quantile(quantile=0.85, window_size=1440).alias(f"{a}_tail_thr") for a in anchors
    ])
    
    # 3. Collective Shock
    # Count how many anchors are in their 85th percentile tail AND have same sign
    df = df.with_columns([
        pl.sum_horizontal([
            ((pl.col(f"{a}_usd") > pl.col(f"{a}_tail_thr"))).cast(pl.Int32) for a in anchors
        ]).alias("tail_count_up"),
        pl.sum_horizontal([
            ((pl.col(f"{a}_usd") < -pl.col(f"{a}_tail_thr"))).cast(pl.Int32) for a in anchors
        ]).alias("tail_count_down")
    ])
    
    print(f"\n>>> COLLECTIVE FORCE TAIL AUDIT (85th Percentile) FOR {dataset_path} <<<")
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: Unanimous (8/8) Individually Significant Tail Shock
    # This is an EXTREME vector event.
    for thr in [7, 8]:
        df_thr = df.with_columns([
            (pl.col("tail_count_up") >= thr).alias("sig_up"), # USD Strong -> Short NSX
            (pl.col("tail_count_down") >= thr).alias("sig_down") # USD Weak -> Long NSX
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_up")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr}/8 Tail Shift      | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_collective_force_audit(f"graph_dataset_1m_{y}.parquet")
