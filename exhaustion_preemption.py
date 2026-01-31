import polars as pl
import numpy as np
import os

def run_exhaustion_preemption():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    # We will test fading USDCHF as it was one of the "Best Losers" in trend-following
    target = 'USDCHF'
    anchors = [n for n in nodes if n != target]
    
    print(f">>> RUNNING EXHAUSTION PREEMPTION (FADING {target}) <<<")
    
    # 1. Macro Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    # 2. Strategy: Fade the Consensus
    # If anchors move UP, we SHORT the target
    CONSENSUS_GO = 7
    
    df = df.with_columns([
        (pl.col("consensus_up") >= CONSENSUS_GO).alias("fade_short"),
        (pl.col("consensus_down") >= CONSENSUS_GO).alias("fade_long")
    ])
    
    # 3. Evaluation (15m horizon)
    # USDCHF spread is usually approx 0.5 bps
    df = df.with_columns(
        (pl.when(pl.col("fade_long")).then( (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 0.5)
          .when(pl.col("fade_short")).then(-(pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 0.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("fade_long") | pl.col("fade_short"))
    if len(results) > 0:
        print(f"\n>>> EXHAUSTION PREEMPTION RESULTS (OOS 2025) <<<")
        print(f"  Target:       {target}")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")

if __name__ == "__main__":
    run_exhaustion_preemption()
