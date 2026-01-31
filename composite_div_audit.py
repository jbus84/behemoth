import polars as pl
import numpy as np
import os

def run_composite_div_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    # We use FX and Metals as the "True Macro" anchors
    anchors = ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'USDJPY', 'USDCHF', 'USDCAD']
    
    print(f"\n>>> MACRO-COMPOSITE DIVERGENCE AUDIT FOR {dataset_path} <<<")
    
    # 1. Macro Composite Trend (USD Centric)
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD']: return -pl.col(f"{pair}_ret_15m")
        else: return pl.col(f"{pair}_ret_15m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd_trend") for a in anchors
    ])
    
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd_trend") for a in anchors]).alias("usd_macro_trend")
    )
    
    # 2. Strategy: Macro-Index Divergence
    # If USD Macro Trend is STRONG UP (> X bps) AND Nasdaq is FLAT/DOWN.
    # Predict: Nasdaq must realign (likely move DOWN to match USD strength).
    # (Note: USD UP = Speculative assets DOWN).
    
    print(f"{'Divergence (bps)':<18} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 70)
    
    for div_bps in [1.0, 2.0, 3.0, 5.0]:
        t = div_bps / 10000
        
        # Signal: Macro Trend > t (USD Strong) AND NSX ret > 0 (NSX is lagging the USD-driven selloff)
        # Trade: SHORT NSX
        df_thr = df.with_columns([
            ((pl.col("usd_macro_trend") > t) & (pl.col("NSXUSD_ret_1m") > 0)).alias("lag_high"),
            ((pl.col("usd_macro_trend") < -t) & (pl.col("NSXUSD_ret_1m") < 0)).alias("lag_low")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("lag_high")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("lag_low")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{div_bps:<18} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_composite_div_audit(f"graph_dataset_1m_{y}.parquet")
