import polars as pl
import numpy as np
import os

def run_evt_tail_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Aligned Macro Force (USD Strength direction)
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    # Aggregate Force (The Pulse intensity)
    df = df.with_columns(
        pl.sum_horizontal([pl.col(f"{a}_usd") for a in anchors]).alias("macro_force")
    )
    
    # 2. EVT Thresholding (Peaks Over Threshold)
    # We use a rolling 1-day window (1440 mins) to find the 99th percentile of macro_force magnitude
    df = df.with_columns([
        pl.col("macro_force").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("force_tail_thr")
    ])
    
    # 3. Strategy: Macro Tail Shock
    # If Macro Force is in the top 1%, trade the direction.
    # We will also test adding the "NSX Stall" filter to isolate the pure lag.
    
    print(f"\n>>> EVT MACRO-TAIL AUDIT (99th Percentile) FOR {dataset_path} <<<")
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    for stall_filter in [False, True]:
        df_strat = df.with_columns([
            (pl.col("macro_force").abs() > pl.col("force_tail_thr")).alias("is_tail")
        ])
        
        # Signals
        # If force > 0 (Extreme USD Strength) -> Short NSX
        # If force < 0 (Extreme USD Weakness) -> Long NSX
        df_strat = df_strat.with_columns([
            (pl.col("is_tail") & (pl.col("macro_force") > 0)).alias("sig_short"),
            (pl.col("is_tail") & (pl.col("macro_force") < 0)).alias("sig_long")
        ])
        
        if stall_filter:
            # Add Paradox-style stall filter
            NSX_STALL = 0.2 / 10000
            df_strat = df_strat.with_columns([
                (pl.col("sig_short") & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_short"),
                (pl.col("sig_long") & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_long")
            ])
            
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = "Tail Only" if not stall_filter else "Tail + NSX Stall"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_evt_tail_audit(f"graph_dataset_1m_{y}.parquet")
