import polars as pl
import numpy as np
import os

def run_session_reversal_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> SESSION REVERSAL AUDIT (FADING SHOCKS) FOR {dataset_path} <<<")
    
    # 1. Session Open Flags (London 8:00 UTC, US 14:30 UTC)
    # Actually, let's just use rolling 15m return anywhere.
    df = df.with_columns([
        pl.col("NSXUSD_ret_15m").alias("shock")
    ])
    
    # 2. Strategy: Fade the Shock
    # If shock > X bps, go SHORT for next 15m.
    
    print(f"{'Shock Thr':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    for thr_bps in [5.0, 10.0, 15.0, 20.0]:
        t = thr_bps / 10000
        
        # PnL = - (target_nsx_15m) if shock > t
        # PnL = + (target_nsx_15m) if shock < -t
        df_thr = df.with_columns(
            (pl.when(pl.col("shock") > t).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("shock") < -t).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_session_reversal_audit(f"graph_dataset_1m_{y}.parquet")
