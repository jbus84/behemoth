import polars as pl
import numpy as np
import os

def run_eur_jpy_lead_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> EUR/JPY CROSS-LEAD AUDIT FOR {dataset_path} <<<")
    
    # 1. Aligned Lead Returns
    # Risk ON = EUR up (EURUSD up) AND JPY down (USDJPY up)
    df = df.with_columns([
        (pl.col("EURUSD_ret_1m") > 0).cast(pl.Int32).alias("eur_up"),
        (pl.col("USDJPY_ret_1m") > 0).cast(pl.Int32).alias("jpy_weak")
    ])
    
    # 2. Strategy: Cross-Lead Consensus
    # If both align (Risk On or Risk Off), trade Nasdaq.
    
    print(f"{'Condition':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    # Signal: Both aligned AND 1m move intensity > Thr
    for thr_bps in [1.0, 2.0, 3.0]:
        t = thr_bps / 10000
        
        df_strat = df.with_columns([
            (pl.col("eur_up") & pl.col("jpy_weak") & (pl.col("EURUSD_ret_1m") > t) & (pl.col("USDJPY_ret_1m") > t)).alias("sig_long"),
            ((1-pl.col("eur_up")) & (1-pl.col("jpy_weak")) & (pl.col("EURUSD_ret_1m") < -t) & (pl.col("USDJPY_ret_1m") < -t)).alias("sig_short")
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"I={thr_bps} bps      | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_eur_jpy_lead_audit(f"graph_dataset_1m_{y}.parquet")
