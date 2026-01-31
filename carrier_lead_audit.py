import polars as pl
import numpy as np
import os

def run_carrier_lead_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> CARRIER LEAD AUDIT (USDJPY -> NSX) FOR {dataset_path} <<<")
    
    # 1. USDJPY Momentum (5m)
    # USDJPY up = Carry trade strength? Actually USDJPY up = JPY weak = Risk ON -> NSX up?
    # Or USDJPY up = USD strong = NSX down?
    # Usually: JPY weakness (USDJPY UP) = Japanese Carry Trade expansion = Global Risk ON = NSX UP.
    
    df = df.with_columns([
        pl.col("USDJPY_ret_5m").alias("jpy_lead")
    ])
    
    print(f"{'JPY Lead Thr':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    for thr_bps in [2.0, 5.0, 10.0]:
        t = thr_bps / 10000
        
        # PnL (15m horizon)
        # If USDJPY UP (t > 0), Long NSX?
        df_thr = df.with_columns(
            (pl.when(pl.col("jpy_lead") > t).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("jpy_lead") < -t).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr_bps:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_carrier_lead_audit(f"graph_dataset_1m_{y}.parquet")
