import polars as pl
import numpy as np
import os

def run_counter_rogue_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> COUNTER-ROGUE FADE AUDIT (120m Reversion) FOR {dataset_path} <<<")
    
    # 1. 120m Aligned Returns
    def usd_ret_120m(pair, df):
        ret = (pl.col(f"{pair}_mid").log() - pl.col(f"{pair}_mid").shift(120).log())
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -ret
        else: return ret
        
    df = df.with_columns([
        usd_ret_120m(n, df).alias(f"{n}_usd_120m") for n in nodes
    ])
    
    # 2. Daily Macro Mean (120m window)
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd_120m") for a in anchors]).alias("macro_mean_120m")
    )
    
    # 3. Nasdaq Rogue Distance (120m)
    df = df.with_columns(
        (pl.col("NSXUSD_usd_120m") - pl.col("macro_mean_120m")).alias("nsx_rogue_120m")
    )
    
    # 4. Target: Next 120m NSX Return
    df = df.with_columns(
        (pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()).alias("target_nsx_120m")
    )
    
    # 5. Q99 Threshold
    df = df.with_columns(
        pl.col("nsx_rogue_120m").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("q99_thr")
    )
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: REVERSION (Fade the Rogue)
    # If NSX > macro mean + Q99: SHORT NSX (Fade the rogue strength).
    # If NSX < macro mean - Q99: LONG NSX (Fade the rogue weakness).
    
    df_strat = df.with_columns([
        ((pl.col("nsx_rogue_120m") > pl.col("q99_thr"))).alias("sig_short"),
        ((pl.col("nsx_rogue_120m") < -pl.col("q99_thr"))).alias("sig_long")
    ])
    
    # PnL (Net 1.5 bps spread)
    df_strat = df_strat.with_columns(
        (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_120m") * 10000 - 1.5)
          .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5) # Error here? Short target or long?
          .otherwise(0)).alias("pnl")
    )
    # Wait, the pnl for short should be - (return). 
    # Let me fix the code for the pnl calculation to be absolutely clear.
    
    df_strat = df.with_columns([
        (pl.when(pl.col("nsx_rogue_120m") > pl.col("q99_thr")).then(-pl.col("target_nsx_120m") * 10000 - 1.5)
          .when(pl.col("nsx_rogue_120m") < -pl.col("q99_thr")).then(pl.col("target_nsx_120m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl")
    ])
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Q99 Rogue Fade       | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_counter_rogue_audit(f"graph_dataset_1m_{y}.parquet")
