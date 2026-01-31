import polars as pl
import numpy as np
import os

def run_vector_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> MULTI-ASSET VECTOR AUDIT (Tension Realign) FOR {dataset_path} <<<")
    
    # 1. Macro Consensus (15m)
    # We use all 9 assets but exclude the target for each test.
    def get_consensus(target, df):
        anchors = [n for n in nodes if n != target]
        def usd_ret(pair, df):
            if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD', 'NSXUSD']: return -pl.col(f"{pair}_ret_15m")
            else: return pl.col(f"{pair}_ret_15m")
        df_tmp = df.with_columns([usd_ret(a, df).alias(f"{a}_usd") for a in anchors])
        up = pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in anchors])
        down = pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in anchors])
        return up, down, pl.mean_horizontal([pl.col(f"{a}_usd") for a in anchors])

    print(f"{'Target':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for target in nodes:
        con_up, con_down, con_mean = get_consensus(target, df)
        
        # Spread map
        spread_map = {
            'NSXUSD': 1.5, 'SPXUSD': 1.5,
            'EURUSD': 0.5, 'GBPUSD': 0.6, 'USDJPY': 0.5,
            'USDCHF': 0.8, 'AUDUSD': 0.6, 'USDCAD': 0.7,
            'XAUUSD': 2.0
        }
        spread = spread_map[target]
        
        # Tension: Target is moving AGAINST consensus
        # Target aligned return
        if target in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD', 'NSXUSD']:
            target_aligned = -pl.col(f"{target}_ret_15m")
        else:
            target_aligned = pl.col(f"{target}_ret_15m")
            
        div = target_aligned - con_mean
        
        # Condition: Consensus 7/8 + Div > 10 bps
        t = 10.0 / 10000
        
        df_strat = df.with_columns([
            ((con_up >= 7) & (div < -t)).alias("sig_up"),
            ((con_down >= 7) & (div > t)).alias("sig_down")
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col(f"target_{target.split('USD')[0].lower()}_15m") * 10000 - spread)
              .when(pl.col("sig_down")).then(-pl.col(f"target_{target.split('USD')[0].lower()}_15m") * 10000 - spread)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{target:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_vector_audit(f"graph_dataset_1m_{y}.parquet")
