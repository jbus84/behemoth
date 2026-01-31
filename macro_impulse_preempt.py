import polars as pl
import numpy as np
import os

def run_impulse_analysis():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING MACRO IMPULSE LEAD/LAG ANALYSIS <<<")
    
    # 1. Define "Macro Impulse"
    # An impulse is a consensus move across the 8 anchors.
    # We use 1-minute returns.
    
    # Track how many anchors are moving in the same direction
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        # Average return of anchors
        pl.mean_horizontal([pl.col(f"{a}_ret_1m") for a in anchors]).alias("macro_ret_avg")
    ])
    
    # 2. Logic: "The Lagged Start"
    # Signal: Extreme Macro Consensus (e.g., 7/8 up) AND NSX hasn't moved yet (Ret < 0.5 bps)
    THRESHOLD_CONSENSUS = 7
    NSX_MAX_MOVE = 0.5 / 10000 # 0.5 bps
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= THRESHOLD_CONSENSUS) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("preempt_long"),
        ((pl.col("consensus_down") >= THRESHOLD_CONSENSUS) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("preempt_short")
    ])
    
    # 3. Evaluation (15m horizon)
    df = df.with_columns(
        (pl.when(pl.col("preempt_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .when(pl.col("preempt_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("preempt_long") | pl.col("preempt_short"))
    
    if len(results) > 0:
        print(f"\n>>> IMPULSE PREEMPTION RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No impulses detected.")

if __name__ == "__main__":
    run_impulse_analysis()
