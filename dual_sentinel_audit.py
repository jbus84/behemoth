import polars as pl
import numpy as np
import os

def run_dual_sentinel_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Consensus Pulse (1m)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("pulse_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("pulse_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol")
    ])
    
    # 2. Dual Gates (9 UTC and 18 UTC)
    # We will also apply the vol filter (< 1 or > 5) to see if it helps
    df = df.with_columns(
        ((pl.col("hour_utc") == 9) | (pl.col("hour_utc") == 18)).alias("dual_window")
    ).with_columns(
        ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0)).alias("vol_fit")
    )
    
    print(f"\n>>> DUAL SENTINEL AUDIT (9/18 UTC) FOR {dataset_path} <<<")
    print(f"{'Consensus':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10}")
    print("-" * 50)
    
    for thr in [7, 8]:
        df_thr = df.with_columns([
            (pl.col("dual_window") & pl.col("vol_fit") & (pl.col("pulse_up") >= thr)).alias("sig_up"),
            (pl.col("dual_window") & pl.col("vol_fit") & (pl.col("pulse_down") >= thr)).alias("sig_down")
        ])
        
        # NSX Lag filter (Quiet entry)
        df_thr = df_thr.with_columns([
            (pl.col("sig_up") & (pl.col("NSXUSD_ret_1m").abs() < 0.2/10000)).alias("final_up"),
            (pl.col("sig_down") & (pl.col("NSXUSD_ret_1m").abs() < 0.2/10000)).alias("final_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("final_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("final_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("final_up") | pl.col("final_down"))
        if len(res) > 0:
            print(f"{thr:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_dual_sentinel_audit(f"graph_dataset_1m_{y}.parquet")
