import polars as pl
import numpy as np
import os

def run_macro_reversion_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> MACRO-CONSENSUS REVERSION AUDIT (120m Fade) FOR {dataset_path} <<<")
    
    # 1. 120m Aligned Returns
    def usd_ret_120m(pair, df):
        ret = (pl.col(f"{pair}_mid").log() - pl.col(f"{pair}_mid").shift(120).log())
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -ret
        else: return ret
        
    df = df.with_columns([
        usd_ret_120m(a, df).alias(f"{a}_usd_120m") for a in anchors
    ])
    
    # 2. Daily Macro Mean Move
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_usd_120m") for a in anchors]).alias("macro_mean_120m")
    )
    
    # 3. Target: Next 120m NSX Return
    df = df.with_columns(
        (pl.col("NSXUSD_mid").shift(-120).log() - pl.col("NSXUSD_mid").log()).alias("target_nsx_120m")
    )
    
    # 4. EVT Threshold on Macro Mean Move
    df = df.with_columns([
        pl.col("macro_mean_120m").abs().rolling_quantile(quantile=0.99, window_size=1440).alias("macro_tail_thr")
    ])
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: IF Collective Macro Move > Q99: SHORT NSX (Fade the macro-driven selloff/rally).
    # Predicts "Consensus Exhaustion".
    
    df_strat = df.with_columns([
        (pl.when(pl.col("macro_mean_120m") > pl.col("macro_tail_thr")).then(pl.col("target_nsx_120m") * 10000 - 1.5) # Macro USD Strong -> Short Assets -> We LONG NSX (Fade)
          .when(pl.col("macro_mean_120m") < -pl.col("macro_tail_thr")).then(-pl.col("target_nsx_120m") * 10000 - 1.5) # Macro USD Weak -> Long Assets -> We SHORT NSX (Fade)
          .otherwise(0)).alias("pnl")
    ])
    
    res = df_strat.filter(pl.col("pnl") != 0)
    if len(res) > 0:
        print(f"Q99 Macro Fade        | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_macro_reversion_audit(f"graph_dataset_1m_{y}.parquet")
