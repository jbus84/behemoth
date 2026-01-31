import polars as pl
import numpy as np
import os

def run_5m_consensus_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> SURGICAL 5m CONSENSUS AUDIT (5m -> 30m) FOR {dataset_path} <<<")
    
    # 1. Calculate 5m returns for anchors
    df = df.with_columns([
        (pl.col(f"{a}_mid").log() - pl.col(f"{a}_mid").shift(5).log()).alias(f"{a}_ret_5m") for a in anchors
    ])
    
    # 2. 5m Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_5m") > 0).cast(pl.Int32) for a in anchors]).alias("pulse_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_5m") < 0).cast(pl.Int32) for a in anchors]).alias("pulse_down")
    ])
    
    # 3. Target: Next 30m NSX Return
    df = df.with_columns(
        (pl.col("NSXUSD_mid").shift(-30).log() - pl.col("NSXUSD_mid").log()).alias("target_30m")
    )
    
    print(f"{'Consensus Thr':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for thr in [7, 8]:
        df_thr = df.with_columns([
            (pl.col("pulse_up") >= thr).alias("sig_up"),
            (pl.col("pulse_down") >= thr).alias("sig_down")
        ])
        
        # PnL (Net 1.5 bps spread)
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("target_30m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(-pl.col("target_30m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_5m_consensus_audit(f"graph_dataset_1m_{y}.parquet")
