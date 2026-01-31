import polars as pl
import numpy as np
import os

def run_spx_lead_analysis():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    # Anchors for SPX (Includes NSX)
    anchors = [n for n in nodes if n != 'SPXUSD']
    
    print(">>> RUNNING FX-LEAD IMPULSE MODEL FOR SPX (PREEMPTION) <<<")
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    # Strategy: Consensus 7/8 AND SPX is quiet
    CONSENSUS_GO = 7
    SPX_MAX_MOVE = 0.2 / 10000 
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("SPXUSD_ret_1m").abs() < SPX_MAX_MOVE)).alias("preempt_long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("SPXUSD_ret_1m").abs() < SPX_MAX_MOVE)).alias("preempt_short")
    ])
    
    # Evaluation
    # Using SPXUSD_spread (assuming it exists in dataset, yes it's added in nodes loop)
    df = df.with_columns(
        (pl.when(pl.col("preempt_long")).then(pl.col("target_spx_15m") * 10000 - pl.col("SPXUSD_spread"))
          .when(pl.col("preempt_short")).then(-pl.col("target_spx_15m") * 10000 - pl.col("SPXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("preempt_long") | pl.col("preempt_short"))
    
    if len(results) > 0:
        print(f"\n>>> SPX-LEAD RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No consensus leads detected for SPX.")

if __name__ == "__main__":
    run_spx_lead_analysis()
