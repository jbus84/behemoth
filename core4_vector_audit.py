import polars as pl
import numpy as np
import os

def run_core4_vector_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    # Core-4 Leaders
    core = ['SPXUSD', 'EURUSD', 'USDJPY', 'XAUUSD']
    
    print(f"\n>>> CORE-4 VECTOR AUDIT (95th Percentile) FOR {dataset_path} <<<")
    
    # 1. Aligned CORE-4 Returns (USD direction)
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'SPXUSD', 'XAUUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(p, df).alias(f"{p}_usd") for p in core
    ])
    
    # 2. Daily Tail Thresholds (95th percentile)
    df = df.with_columns([
        pl.col(f"{p}_usd").abs().rolling_quantile(quantile=0.95, window_size=1440).alias(f"{p}_tail_thr") for p in core
    ])
    
    # 3. Strategy: Unanimous Tail Shock
    # All 4 moving in same USD direction AND all 4 are in their 95th percentile tail.
    
    print(f"{'Condition':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    df_sig = df.with_columns([
        (pl.all_horizontal([pl.col(f"{p}_usd") > pl.col(f"{p}_tail_thr") for p in core])).alias("sig_up"),
        (pl.all_horizontal([pl.col(f"{p}_usd") < -pl.col(f"{p}_tail_thr") for p in core])).alias("sig_down")
    ])
    
    df_sig = df_sig.with_columns(
        (pl.when(pl.col("sig_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("sig_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_sig.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Core-4 Q95      | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_core4_vector_audit(f"graph_dataset_1m_{y}.parquet")
