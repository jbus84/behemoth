import polars as pl
import numpy as np
import os

def run_vol_flip_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> INTRADAY VOLATILITY FLIP AUDIT FOR {dataset_path} <<<")
    
    df = df.with_columns([
        pl.col("timestamp").dt.date().alias("date"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_ret_1m").alias("ret_1m")
    ])
    
    # 1. Morning Volatility (08:00 - 12:00 UTC)
    df_morning = df.filter(pl.col("hour_utc").is_between(8, 12))
    df_vol = df_morning.group_by("date").agg(
        pl.col("ret_1m").std().alias("morning_vol")
    )
    
    # 2. Afternoon Returns (14:00 - 16:00 UTC)
    # We test a simple 15m consensus follow strategy gated by morning vol.
    df = df.join(df_vol, on="date")
    
    # Calculate Macro Consensus (1m)
    nodes = ['SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in nodes
    ])
    
    df = df.with_columns(
        pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in nodes]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in nodes]).alias("con_down")
    )
    
    # 3. Audit: Afternoon Momentum (14:00 - 17:00 UTC)
    df_afternoon = df.filter(pl.col("hour_utc").is_between(14, 17))
    
    # Daily Vol Median for gating
    vol_median = df_vol['morning_vol'].median()
    
    print(f"Morning Vol Median: {vol_median:.6f}")
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    for gate in ['Low Vol', 'High Vol']:
        if gate == 'Low Vol': df_gated = df_afternoon.filter(pl.col("morning_vol") < vol_median)
        else: df_gated = df_afternoon.filter(pl.col("morning_vol") >= vol_median)
        
        # Strategy: Momentum (7/8 Consensus)
        df_strat = df_gated.with_columns(
            (pl.when(pl.col("con_up") >= 7).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("con_down") >= 7).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"{gate} Momo"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_vol_flip_audit(f"graph_dataset_1m_{y}.parquet")
