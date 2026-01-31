import polars as pl
import numpy as np
import os

def run_basket_dispersion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Aligned Macro returns
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in anchors
    ])
    
    # 2. Daily Dispersion (Rolling Std Dev of the 8 aligned anchors)
    df = df.with_columns(
        pl.concat_list([pl.col(f"{a}_usd") for a in anchors]).list.std().alias("macro_dispersion")
    )
    
    # 3. EVT Threshold on Dispersion
    # High dispersion = extreme internal conflict in the macro field.
    df = df.with_columns([
        pl.col("macro_dispersion").rolling_quantile(quantile=0.95, window_size=1440).alias("disp_tail_thr")
    ])
    
    print(f"\n>>> BASKET DISPERSION EVT AUDIT (95th Percentile) FOR {dataset_path} <<<")
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: If Dispersion is extreme, find the "Rogue" (Asset most different from mean).
    # If Nasdaq is the Rogue, trade it back to the Mean.
    
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd") for a in anchors]).alias("macro_mean")
    )
    
    # Nasdaq Alignment
    df = df.with_columns(
        (-pl.col("NSXUSD_ret_1m")).alias("nsx_usd_aligned")
    )
    
    # Nasdaq Rogue Distance
    df = df.with_columns(
        (pl.col("nsx_usd_aligned") - pl.col("macro_mean")).alias("nsx_rogue_dist")
    )
    
    # Strategy: Dispersion > Tail AND NSX is a Rogue (> 2 std devs from macro mean or > Thr)
    for thr_bps in [2.0, 5.0]:
        t = thr_bps / 10000
        
        df_thr = df.with_columns([
            ((pl.col("macro_dispersion") > pl.col("disp_tail_thr")) & (pl.col("nsx_rogue_dist") > t)).alias("nsx_overextended"), # SHORT NSX
            ((pl.col("macro_dispersion") > pl.col("disp_tail_thr")) & (pl.col("nsx_rogue_dist") < -t)).alias("nsx_lagging")     # LONG NSX
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("nsx_overextended")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("nsx_lagging")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"Rogue Dist {thr_bps} bps | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_basket_dispersion_audit(f"graph_dataset_1m_{y}.parquet")
