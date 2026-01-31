import polars as pl
import numpy as np
import os

def run_correlation_gate_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> CORRELATION GATE AUDIT FOR {dataset_path} <<<")
    
    # 1. Aligned 1m Returns
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd") for a in anchors]).alias("macro_mean")
    )
    
    # 2. 60m Rolling Correlation (NSX vs Macro)
    df = df.with_columns(
        pl.rolling_corr(pl.col("NSXUSD_ret_1m"), pl.col("macro_mean"), window_size=60).alias("m_corr")
    )
    
    # 3. Targets
    df = df.with_columns(
        pl.col("target_nsx_15m").alias("target")
    )
    
    # 4. Filter: High-Energy Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in anchors]).alias("con_down")
    ])
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy A: HIGH CORR -> FOLLOW THE CONCENSUS (Momentum)
    # Strategy B: LOW CORR -> FADE THE CONCENSUS (Mean Reversion)
    
    for c_thr in [0.7, 0.3]:
        if c_thr > 0.5:
            label = f"Corr > {c_thr} (Momo)"
            df_strat = df.with_columns(
                (pl.when((pl.col("m_corr") > c_thr) & (pl.col("con_up") >= 7)).then(pl.col("target") * 10000 - 1.5)
                  .when((pl.col("m_corr") > c_thr) & (pl.col("con_down") >= 7)).then(-pl.col("target") * 10000 - 1.5)
                  .otherwise(0)).alias("pnl")
            )
        else:
            label = f"Corr < {c_thr} (Revert)"
            df_strat = df.with_columns(
                (pl.when((pl.col("m_corr") < c_thr) & (pl.col("con_up") >= 7)).then(-pl.col("target") * 10000 - 1.5)
                  .when((pl.col("m_corr") < c_thr) & (pl.col("con_down") >= 7)).then(pl.col("target") * 10000 - 1.5)
                  .otherwise(0)).alias("pnl")
            )
            
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_correlation_gate_audit(f"graph_dataset_1m_{y}.parquet")
