import polars as pl
import numpy as np
import os

def run_momentum_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. 15m Momentum Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_15m") > 0).cast(pl.Int32) for a in anchors]).alias("mom_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_15m") < 0).cast(pl.Int32) for a in anchors]).alias("mom_down")
    ])
    
    # 2. Target: Next 15m NSX Return
    # (Note: graph_dataset already has target_nsx_15m which is mid.shift(-15).log - mid.log)
    
    print(f"\n>>> MOMENTUM AUDIT FOR {dataset_path} (15m Consensus) <<<")
    print(f"{'Threshold':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10}")
    print("-" * 50)
    
    for thr in [5, 6, 7, 8]:
        df_thr = df.with_columns([
            (pl.col("mom_up") >= thr).alias("sig_up"),
            (pl.col("mom_down") >= thr).alias("sig_down")
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
        run_momentum_audit(f"graph_dataset_1m_{y}.parquet")
