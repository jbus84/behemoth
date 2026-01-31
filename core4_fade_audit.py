import polars as pl
import numpy as np
import os

def run_core4_fade_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    # Core-4 Leaders
    core = ['SPXUSD', 'EURUSD', 'USDJPY', 'XAUUSD']
    
    print(f"\n>>> CORE-4 MACRO FADE AUDIT FOR {dataset_path} <<<")
    
    # 1. Aligned CORE-4 Returns (USD direction)
    # USD Strength direction: SPX Down, EUR Down, JPY Up, XAU Down
    df = df.with_columns([
        (pl.col("SPXUSD_ret_1m") < 0).cast(pl.Int32).alias("spx_usd_up"),
        (pl.col("EURUSD_ret_1m") < 0).cast(pl.Int32).alias("eur_usd_up"),
        (pl.col("USDJPY_ret_1m") > 0).cast(pl.Int32).alias("jpy_usd_up"),
        (pl.col("XAUUSD_ret_1m") < 0).cast(pl.Int32).alias("xau_usd_up")
    ])
    
    df = df.with_columns([
        pl.sum_horizontal([pl.col("spx_usd_up"), pl.col("eur_usd_up"), pl.col("jpy_usd_up"), pl.col("xau_usd_up")]).alias("core_up"),
        (4 - pl.sum_horizontal([pl.col("spx_usd_up"), pl.col("eur_usd_up"), pl.col("jpy_usd_up"), pl.col("xau_usd_up")])).alias("core_down")
    ])
    
    # 2. Strategy: Fade the Core-4 Unanimity (4/4)
    # If 4/4 Core-4 are UP (USD Strong), predict NSX is over-sold -> LONG NSX
    # If 4/4 Core-4 are DOWN (USD Weak), predict NSX is over-bought -> SHORT NSX
    
    print(f"{'Condition':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    df_sig = df.with_columns([
        (pl.col("core_up") == 4).alias("sig_fade_down"), # USD Strong move into NSX. We LONG NSX.
        (pl.col("core_down") == 4).alias("sig_fade_up")    # USD Weak move into NSX. We SHORT NSX.
    ])
    
    df_sig = df_sig.with_columns(
        (pl.when(pl.col("sig_fade_down")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("sig_fade_up")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    )
    
    res = df_sig.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Core-4 Unanimous | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_core4_fade_audit(f"graph_dataset_1m_{y}.parquet")
