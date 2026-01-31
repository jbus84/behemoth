import polars as pl
import numpy as np
import os

def run_consensus_tail_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Aligned 1m Consensus Mean
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd") for a in anchors]).alias("v_mean")
    )
    
    print(f"\n>>> CONSENSUS TAIL AUDIT (Q99) FOR {dataset_path} <<<")
    
    # 2. Daily Tail Threshold on v_mean
    df = df.with_columns([
        pl.col("v_mean").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("v_tail_thr")
    ])
    
    # 3. Strategy: Follow the Extreme Vector
    print(f"{'Condition':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    df_strat = df.with_columns(
        (pl.when(pl.col("v_mean") > pl.col("v_tail_thr")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("v_mean") < -pl.col("v_tail_thr")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Vector Q99       | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_consensus_tail_audit(f"graph_dataset_1m_{y}.parquet")
