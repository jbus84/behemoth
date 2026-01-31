import polars as pl
import numpy as np
import os

def run_correlation_drift_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> MICRO-CORRELATION DRIFT AUDIT (AUD vs CAD) FOR {dataset_path} <<<")
    
    # 1. Commodity Basket Lead
    # AUD up = CAD down (usually).
    # Drift = (AUD_ret - CAD_ret). If drift > X, commodities are strong -> NSX up?
    df = df.with_columns(
        (pl.col("AUDUSD_ret_1m") - pl.col("USDCAD_ret_1m")).alias("commodity_drift")
    )
    
    # 2. Logic: If Commodity Drift > Thr, Long NSX
    
    print(f"{'Drift Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for d_bps in [1.0, 2.0, 3.0, 5.0]:
        t = d_bps / 10000
        
        df_thr = df.with_columns([
            (pl.col("commodity_drift") > t).alias("sig_long"),
            (pl.col("commodity_drift") < -t).alias("sig_short")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{d_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_correlation_drift_audit(f"graph_dataset_1m_{y}.parquet")
