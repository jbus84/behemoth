import polars as pl
import numpy as np
import os

def run_spx_lead_reversion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> SPX LEAD-LAG REVERSION AUDIT FOR {dataset_path} <<<")
    
    # 1. SPX shock (1m)
    df = df.with_columns([
        pl.col("SPXUSD_ret_1m").alias("spx_shock")
    ])
    
    # 2. Strategy: Fade the SPX Shock
    # If SPX moves > Thr, go AGAINST it in NSX.
    
    print(f"{'SPX Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for thr_bps in [2.0, 3.0, 5.0]:
        t = thr_bps / 10000
        
        # PnL (15m horizon)
        df_thr = df.with_columns(
            (pl.when(pl.col("spx_shock") > t).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("spx_shock") < -t).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_spx_lead_reversion_audit(f"graph_dataset_1m_{y}.parquet")
