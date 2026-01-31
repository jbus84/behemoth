import polars as pl
import numpy as np
import os

def run_long_rogue_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> LONG-HORIZON ROGUE EVT AUDIT (120m) FOR {dataset_path} <<<")
    
    # 1. 120m Aligned Returns
    def usd_ret_120m(pair, df):
        # We need to calculate 120m returns
        ret = (pl.col(f"{pair}_mid").log() - pl.col(f"{pair}_mid").shift(120).log())
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -ret
        else: return ret
        
    df = df.with_columns([
        usd_ret_120m(n, df).alias(f"{n}_usd_120m") for n in nodes
    ])
    
    # 2. Daily Macro Mean & Dispersion (120m window)
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd_120m") for a in anchors]).alias("macro_mean_120m")
    )
    
    # 3. Nasdaq Rogue Distance (120m)
    df = df.with_columns(
        (pl.col("NSXUSD_usd_120m") - pl.col("macro_mean_120m")).alias("nsx_rogue_120m")
    )
    
    # 4. EVT Threshold (95th/99th Percentile)
    df = df.with_columns([
        pl.col("nsx_rogue_120m").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("rogue_tail_thr")
    ])
    
    # 5. Target: Next 120m NSX Return Relative to Macro Mean
    # Actually, let's just use the NSX leg for execution.
    df = df.with_columns(
        (pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()).alias("target_nsx_120m")
    )
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: NSX is an extreme outlier on 2-hour window. Fade it.
    for q in [0.95, 0.99]:
        df = df.with_columns(
            pl.col("nsx_rogue_120m").abs().rolling_quantile(quantile=q, window_size=1440).alias("q_thr")
        )
        
        df_strat = df.with_columns([
            ((pl.col("nsx_rogue_120m") > pl.col("q_thr"))).alias("too_strong"), # SHORT NSX
            ((pl.col("nsx_rogue_120m") < -pl.col("q_thr"))).alias("too_weak")    # LONG NSX
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("too_weak")).then(pl.col("target_nsx_120m") * 10000 - 1.5)
              .when(pl.col("too_strong")).then(-pl.col("target_nsx_120m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"Q {int(q*100)} Tail"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_long_rogue_audit(f"graph_dataset_1m_{y}.parquet")
