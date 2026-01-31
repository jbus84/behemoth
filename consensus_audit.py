import polars as pl
import numpy as np
import os

def audit_consensus_thresholds(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    print(f"\n>>> THRESHOLD AUDIT FOR {dataset_path} <<<")
    print(f"{'Threshold':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10}")
    print("-" * 45)
    
    for thr in [5, 6, 7, 8]:
        # Filter (No session/vol gating for raw alpha check)
        df_thr = df.with_columns([
            (pl.col("consensus_up") >= thr).alias("sig_up"),
            (pl.col("consensus_down") >= thr).alias("sig_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("sig_up") | pl.col("sig_down"))
        if len(res) > 0:
            print(f"{thr:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        audit_consensus_thresholds(f"graph_dataset_1m_{y}.parquet")
