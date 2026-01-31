import polars as pl
import numpy as np
import os

def run_persistence_gate_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(f"\n>>> PERSISTENCE GATE AUDIT (Q99 + Consensus) FOR {dataset_path} <<<")
    
    # 1. 120m Aligned Returns
    def usd_ret_120m(pair, df):
        ret = (pl.col(f"{pair}_mid").log() - pl.col(f"{pair}_mid").shift(120).log())
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']: return -ret
        else: return ret
        
    df = df.with_columns([
        usd_ret_120m(n, df).alias(f"{n}_usd_120m") for n in nodes
    ])
    
    # 2. Macro Consensus (120m)
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd_120m") > 0).cast(pl.Int32) for a in anchors]).alias("con_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd_120m") < 0).cast(pl.Int32) for a in anchors]).alias("con_down")
    ])
    
    # 3. Nasdaq Rogue Distance (120m)
    df = df.with_columns(
        (pl.col("NSXUSD_usd_120m") - pl.mean_horizontal([pl.col(f"{a}_usd_120m") for a in anchors])).alias("nsx_rogue_120m")
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
    
    # Strategy: IF Rogue > Q99 AND UNANIMOUS (7/8) Consensus in same direction.
    # Predicts "Extreme Wave Persistence".
    
    for con_thr in [6, 7, 8]:
        df_strat = df.with_columns([
            ((pl.col("nsx_rogue_120m") > pl.col("q99_thr")) & (pl.col("con_up") >= con_thr)).alias("sig_long"), # Macro UP + NSX Leading UP -> Follow
            ((pl.col("nsx_rogue_120m") < -pl.col("q99_thr")) & (pl.col("con_down") >= con_thr)).alias("sig_short") # Macro DOWN + NSX Leading DOWN -> Follow
        ])
        
        df_strat = df_strat.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_120m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_120m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"Q99 + {con_thr}/8 Con"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_persistence_gate_audit(f"graph_dataset_1m_{y}.parquet")
