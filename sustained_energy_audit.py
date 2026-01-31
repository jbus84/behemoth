import polars as pl
import numpy as np
import os

def run_sustained_energy_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> SUSTAINED ENERGY AUDIT (5m Integral) FOR {dataset_path} <<<")
    
    # 1. Aligned 1m Consensus
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in anchors]).alias("con_down")
    ])
    
    # 2. 5-Minute Integral (Sustained Consensus)
    df = df.with_columns([
        pl.col("con_up").rolling_sum(window_size=5).alias("int_up"),
        pl.col("con_down").rolling_sum(window_size=5).alias("int_down")
    ])
    
    # Max possible int is 5 * 8 = 40.
    
    print(f"{'Integral Thr':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for thr in [30, 35, 38]:
        df_thr = df.with_columns([
            (pl.col("int_up") >= thr).alias("sig_long"),
            (pl.col("int_down") >= thr).alias("sig_short")
        ])
        
        # PnL (15m horizon)
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{thr:<15} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_sustained_energy_audit(f"graph_dataset_1m_{y}.parquet")
