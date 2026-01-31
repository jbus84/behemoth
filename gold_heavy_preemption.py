import polars as pl
import numpy as np
import os

def run_gold_heavy_preemption():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    target = 'XAUUSD'
    anchors = [n for n in nodes if n != target]
    
    print(f">>> RUNNING GOLD HEAVY PREEMPTION (TARGET: {target}) <<<")
    
    # 1. Macro Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc")
    ])
    
    # 2. Strategy: The London Fix Force
    # Window: 14:00 - 16:00 UTC (The London Fix / US Open overlap)
    CONSENSUS_GO = 8 # UNANIMOUS force
    
    df = df.with_columns(
        (pl.col("hour_utc").is_between(14, 16)).alias("fix_window")
    )
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & pl.col("fix_window")).alias("long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & pl.col("fix_window")).alias("short")
    ])
    
    # 3. Evaluation (15m)
    # Gold spread is approx 2.0 bps
    df = df.with_columns(
        (pl.when(pl.col("long")).then( (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 2.0)
          .when(pl.col("short")).then(-(pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 2.0)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("long") | pl.col("short"))
    if len(results) > 0:
        print(f"\n>>> GOLD HEAVY RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No unanimous gold leads detected.")

if __name__ == "__main__":
    run_gold_heavy_preemption()
