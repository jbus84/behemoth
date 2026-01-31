import polars as pl
import numpy as np
import os

def run_absolute_zero_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> ABSOLUTE ZERO LAG AUDIT FOR {dataset_path} <<<")
    
    # 1. Consensus & Energy (1m)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("con_down"),
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("energy")
    ])
    
    # 2. Logic: The Zero Gating
    # We require NSX return to be exactly 0.00 (frozen)
    NSX_STALL = 1e-9 # Float zero
    
    print(f"{'Energy Thr (bps)':<18} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 70)
    
    for e_bps in [1.0, 2.0, 3.0, 5.0]:
        t = e_bps / 10000
        
        df_strat = df.with_columns([
            ((pl.col("con_up") >= 7) & (pl.col("energy") > t) & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_up"),
            ((pl.col("con_down") >= 7) & (pl.col("energy") > t) & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_down")
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"E={e_bps} bps      | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_absolute_zero_audit(f"graph_dataset_1m_{y}.parquet")
