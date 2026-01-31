import polars as pl
import numpy as np
import os

def run_rogue_wave_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> 60m ROGUE WAVE AUDIT FOR {dataset_path} <<<")
    
    # 1. 60m Index Return Divergence
    df = df.with_columns([
        (pl.col("NSXUSD_mid").log() - pl.col("NSXUSD_mid").shift(60).log()).alias("nsx_60m"),
        (pl.col("SPXUSD_mid").log() - pl.col("SPXUSD_mid").shift(60).log()).alias("spx_60m")
    ])
    
    df = df.with_columns(
        (pl.col("nsx_60m") - pl.col("spx_60m")).alias("div_60m")
    )
    
    # 2. Target: Next 60m NSX Return
    df = df.with_columns(
        (pl.col("NSXUSD_mid").shift(-60).log() - pl.col("NSXUSD_mid").log()).alias("target_60m")
    )
    
    print(f"{'Div Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for div_bps in [5.0, 10.0, 15.0]:
        t = div_bps / 10000
        
        # Strategy: Follow the 60m Rogue Breakout
        df_strat = df.with_columns([
            (pl.col("div_60m") > t).alias("sig_long"),
            (pl.col("div_60m") < -t).alias("sig_short")
        ])
        
        # PnL (Net 1.5 bps spread)
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_60m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_60m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{div_bps:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_rogue_wave_audit(f"graph_dataset_1m_{y}.parquet")
