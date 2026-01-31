import polars as pl
import numpy as np
import os

def run_intensity_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> ROGUE INTENSITY AUDIT FOR {dataset_path} <<<")
    
    # 1. Macro Consensus (1m)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("con_down")
    ])
    
    # 2. Rogue Distance (15m Relative to SPX)
    df = df.with_columns(
        (pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")).alias("nsx_spx_div")
    )
    
    print(f"{'Tension (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for thr_bps in [10.0, 15.0, 20.0, 25.0]:
        t = thr_bps / 10000
        
        # Strategy: Consensus 7/8 + Outlier Resistance > t
        df_thr = df.with_columns([
            ((pl.col("con_up") >= 7) & (pl.col("nsx_spx_div") < -t)).alias("sig_up"),
            ((pl.col("con_down") >= 7) & (pl.col("nsx_spx_div") > t)).alias("sig_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_intensity_audit(f"graph_dataset_1m_{y}.parquet")
