import polars as pl
import numpy as np
import os

def run_collective_vol_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> COLLECTIVE VOLATILITY REVERSION AUDIT FOR {dataset_path} <<<")
    
    # 1. Aggregate Macro Volatility
    # (Assuming _vol_30m features exist for anchors in the dataset)
    # If not, we'll calculate them. 
    # Let me check column names first.
    
    cols = df.columns
    if not all(f"{a}_vol_30m" in cols for a in anchors):
        print("Required volatility features missing. Calculating...")
        df = df.with_columns([
            (pl.col(f"{a}_mid").log() - pl.col(f"{a}_mid").shift(1).log()).alias(f"{a}_ret_1m") for a in anchors
        ])
        df = df.with_columns([
            (pl.col(f"{a}_ret_1m").rolling_std(window_size=30) * 10000).alias(f"{a}_vol_30m") for a in anchors
        ])
        
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_vol_30m") for a in anchors]).alias("macro_vol_mean")
    )
    
    # 2. EVT Threshold on Macro Vol
    df = df.with_columns([
        pl.col("macro_vol_mean").rolling_quantile(quantile=0.99, window_size=1440).alias("vol_tail_thr")
    ])
    
    # 3. Strategy: Fade the Peak Chaos
    # If Vol > Tail AND 1m Move exists. Fade the move.
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    df_strat = df.with_columns(
        (pl.when((pl.col("macro_vol_mean") > pl.col("vol_tail_thr")) & (pl.col("NSXUSD_ret_1m") > 0))
          .then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .when((pl.col("macro_vol_mean") > pl.col("vol_tail_thr")) & (pl.col("NSXUSD_ret_1m") < 0))
          .then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Global Vol Peak (Q99) | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_collective_vol_audit(f"graph_dataset_1m_{y}.parquet")
