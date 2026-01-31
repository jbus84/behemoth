import polars as pl
import numpy as np
import os

def run_ghost_pulse_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> GHOST PULSE AUDIT FOR {dataset_path} <<<")
    
    # 1. Consensus Pulse (1m)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("pulse_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("pulse_down"),
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("macro_energy")
    ])
    
    # 2. The Ghost Gating (Absolute Zero)
    # We require NSX return to be exactly 0.0 or < smallest possible tick.
    NSX_ZERO = 1e-9
    
    print(f"{'Energy Thr':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 60)
    
    # UNANIMOUS
    CONSENSUS_GO = 8
    
    for nrg in [1.0, 2.0, 3.0, 5.0]:
        e_thr = nrg / 10000
        
        df_thr = df.with_columns([
            ((pl.col("pulse_up") >= CONSENSUS_GO) & (pl.col("macro_energy") > e_thr) & (pl.col("NSXUSD_ret_1m").abs() < NSX_ZERO)).alias("sig_up"),
            ((pl.col("pulse_down") >= CONSENSUS_GO) & (pl.col("macro_energy") > e_thr) & (pl.col("NSXUSD_ret_1m").abs() < NSX_ZERO)).alias("sig_down")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{nrg:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_ghost_pulse_audit(f"graph_dataset_1m_{y}.parquet")
