import polars as pl
import numpy as np
import os

def audit_slingshot_sensitivity(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc")
    ]).filter(pl.col("hour_utc").is_between(12, 20))
    
    print(f"\n>>> SLINGSHOT SENSITIVITY AUDIT FOR {dataset_path} <<<")
    print(f"{'Div Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10}")
    print("-" * 50)
    
    CONSENSUS_GO = 7
    
    for div_bps in [0.5, 1.0, 1.5, 2.0]:
        thr = div_bps / 10000
        
        df_audit = df.with_columns([
            ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") < -thr)).alias("long"),
            ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") > thr)).alias("short")
        ])
        
        df_audit = df_audit.with_columns(
            (pl.when(pl.col("long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_audit.filter(pl.col("long") | pl.col("short"))
        if len(res) > 0:
            print(f"{div_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        audit_slingshot_sensitivity(f"graph_dataset_1m_{y}.parquet")
