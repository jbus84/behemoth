import polars as pl
import numpy as np
import os

def run_double_negative_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> DOUBLE-NEGATIVE ROGUE AUDIT (Tension Realign) FOR {dataset_path} <<<")
    
    # 1. 15m Macro Consensus (Strong)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_15m") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_15m") < 0).cast(pl.Int32) for a in anchors]).alias("con_down")
    ])
    
    # 2. 15m Nasdaq Rogue (Relative to SPX - closer proxy)
    df = df.with_columns(
        (pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")).alias("nsx_spx_div")
    )
    
    # 3. Target: Next 15m NSX Return
    df = df.with_columns(
        pl.col("target_nsx_15m").alias("target")
    )
    
    # 4. Filter: CONFLICT
    # Macro consensus is UP (7/8) but NSX is severely lagging SPX (< -2 bps)
    # Predict: NSX must SNAP UP to realign.
    
    print(f"{'Div Thr (bps)':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for div_thr in [2.0, 5.0, 10.0]:
        t = div_thr / 10000
        
        df_strat = df.with_columns([
            ((pl.col("con_up") >= 7) & (pl.col("nsx_spx_div") < -t)).alias("sig_snap_up"), # Macro Up, NSX Lagging -> Long
            ((pl.col("con_down") >= 7) & (pl.col("nsx_spx_div") > t)).alias("sig_snap_down") # Macro Down, NSX Leading -> Short
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_snap_up")).then(pl.col("target") * 10000 - 1.5)
              .when(pl.col("sig_snap_down")).then(-pl.col("target") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{div_thr:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_double_negative_audit(f"graph_dataset_1m_{y}.parquet")
