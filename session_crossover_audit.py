import polars as pl
import numpy as np
import os

def run_session_crossover_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> SESSION CROSSOVER AUDIT (London -> NY) FOR {dataset_path} <<<")
    
    df = df.with_columns([
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        (pl.col("NSXUSD_mid").log() - pl.col("NSXUSD_mid").shift(240).log()).alias("london_trend")
    ])
    
    # Snapshot at 13:30 (NY Open / Morning)
    df_ny = df.filter((pl.col("hour_utc") == 13) & (pl.col("timestamp").dt.minute() == 30))
    
    # Target: Next 120m
    df_ny = df_ny.with_columns(
        (pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()).alias("ny_target")
    )
    
    print(f"{'London Trend (bps)':<20} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    for tr in [20, 50, 80]:
        t = tr / 10000
        
        # Continuation
        df_cont = df_ny.with_columns(
            (pl.when(pl.col("london_trend") > t).then(pl.col("ny_target") * 10000 - 1.5)
              .when(pl.col("london_trend") < -t).then(-pl.col("ny_target") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        res_c = df_cont.filter(pl.col("pnl") != 0)
        if len(res_c) > 0:
            print(f"T > {tr} bps (Cont)    | {len(res_c):<8} | { (res_c['pnl'] > 0).mean()*100:>8.2f}% | {res_c['pnl'].mean():>8.3f} bps")
            
        # Reversion
        df_rev = df_ny.with_columns(
            (pl.when(pl.col("london_trend") > t).then(-pl.col("ny_target") * 10000 - 1.5)
              .when(pl.col("london_trend") < -t).then(pl.col("ny_target") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        res_r = df_rev.filter(pl.col("pnl") != 0)
        if len(res_r) > 0:
            print(f"T > {tr} bps (Rev)     | {len(res_r):<8} | { (res_r['pnl'] > 0).mean()*100:>8.2f}% | {res_r['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_session_crossover_audit(f"graph_dataset_1m_{y}.parquet")
