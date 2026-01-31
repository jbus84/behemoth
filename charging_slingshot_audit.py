import polars as pl
import numpy as np
import os

def run_charging_slingshot_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> CHARGING SLINGSHOT AUDIT (15m Charge) FOR {dataset_path} <<<")
    
    # 1. 15m Macro Drift
    def usd_ret_15m(pair, df):
        ret = (pl.col(f"{pair}_mid").log() - pl.col(f"{pair}_mid").shift(15).log())
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -ret
        else: return ret
        
    df = df.with_columns([
        usd_ret_15m(a, df).alias(f"{a}_usd_15m") for a in nodes
    ])
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd_15m") > 0).cast(pl.Int32) for a in nodes]).alias("drift_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd_15m") < 0).cast(pl.Int32) for a in nodes]).alias("drift_down")
    ])
    
    # 2. 15m Nasdaq Range (The Charging Stall)
    # Max High - Min Low over last 15 mins
    df = df.with_columns([
        (pl.col("NSXUSD_mid").rolling_max(window_size=15).log() - pl.col("NSXUSD_mid").rolling_min(window_size=15).log()).alias("nsx_range_15m")
    ])
    
    # 3. Strategy: 15m Consensus Drift (7/8) AND NSX Range < Thr
    NSX_QUIET = 2.0 / 10000 # 2 bps range over 15 mins is very quiet
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    df_strat = df.with_columns(
        (pl.when((pl.col("drift_up") >= 7) & (pl.col("nsx_range_15m") < NSX_QUIET)).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when((pl.col("drift_down") >= 7) & (pl.col("nsx_range_15m") < NSX_QUIET)).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"15m Charging Slingshot | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_charging_slingshot_audit(f"graph_dataset_1m_{y}.parquet")
