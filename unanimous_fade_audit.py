import polars as pl
import numpy as np
import os

def run_unanimous_fade_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> UNANIMOUS FADE AUDIT (8/8) FOR {dataset_path} <<<")
    
    # 1. Consensus (1m)
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in anchors]).alias("v_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in anchors]).alias("v_down")
    ])
    
    # 2. Strategy: Unanimous Fade
    print(f"{'Condition':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    df_strat = df.with_columns(
        (pl.when(pl.col("v_up") == 8).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("v_down") == 8).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"8/8 Fade        | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_unanimous_fade_audit(f"graph_dataset_1m_{y}.parquet")
