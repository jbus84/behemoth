import polars as pl
import numpy as np
import os

def run_london_close_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> LONDON CLOSE REVERSAL AUDIT (16:00 - 17:00 UTC) FOR {dataset_path} <<<")
    
    # 1. Detect the Trend into the Close
    # We look at the return from 15:30 to 16:30 UTC
    df = df.with_columns([
        pl.col("timestamp").dt.hour().alias("hour"),
        pl.col("timestamp").dt.minute().alias("minute")
    ])
    
    # 2. Logic: At 16:30 UTC, if last 60m return > Thr, Fade it for 30m.
    # (London Close is 16:30 UTC usually, sometimes 15:30 in DST, but 16:30 is the 'Benchmark').
    
    print(f"{'Trend Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for thr_bps in [10.0, 20.0, 30.0]:
        t = thr_bps / 10000
        
        # We only evaluate at 16:30 UTC
        filter_mask = (pl.col("hour") == 16) & (pl.col("minute") == 30)
        
        # Trend into close (last 60m)
        df_audit = df.with_columns([
            (pl.col("NSXUSD_mid").log() - pl.col("NSXUSD_mid").shift(60).log()).alias("trend_in")
        ])
        
        # PnL (Next 30m)
        df_audit = df_audit.with_columns([
            (pl.col("NSXUSD_mid").shift(-30).log() - pl.col("NSXUSD_mid").log()).alias("return_out")
        ])
        
        df_audit = df_audit.filter(filter_mask)
        
        df_audit = df_audit.with_columns(
            (pl.when(pl.col("trend_in") > t).then(-pl.col("return_out") * 10000 - 1.5)
              .when(pl.col("trend_in") < -t).then(pl.col("return_out") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_audit.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_london_close_audit(f"graph_dataset_1m_{y}.parquet")
