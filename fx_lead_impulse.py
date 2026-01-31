import polars as pl
import numpy as np
import os

def run_fx_lead_analysis():
    # We use the 1m dataset as the base
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    # 8 Macro Anchors that we assume LEAD the NSX
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING FX-LEAD IMPULSE MODEL (PREEMPTION) <<<")
    
    # 1. Define "Macro Momentum"
    # A consensus momentum pulse across FX/Gold/S&P
    # We count how many assets are in a positive/negative return state
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        # Magnitude check: Are the moves big enough to be a 'Lead'?
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("avg_macro_move")
    ])
    
    # 2. Strategy: The Delayed Reaction
    # Signal: Extreme Macro Consensus (8 out of 8 assets)
    # We enter the trade for a 15-minute horizon
    CONSENSUS_GO = 8 
    NSX_MAX_MOVE = 0.2 / 10000 
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("preempt_long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("preempt_short")
    ])
    
    # 3. Evaluation
    df = df.with_columns(
        (pl.when(pl.col("preempt_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .when(pl.col("preempt_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("preempt_long") | pl.col("preempt_short"))
    
    if len(results) > 0:
        print(f"\n>>> FX-LEAD RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No consensus leads detected.")

if __name__ == "__main__":
    run_fx_lead_analysis()
