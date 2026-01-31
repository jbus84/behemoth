import polars as pl
import numpy as np
import os

def run_paradox_sentinel(dataset_path):
    if not os.path.exists(dataset_path):
        print(f"Dataset {dataset_path} missing.")
        return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Macro Signal Engine
    df = df.with_columns([
        # Consensus Direction
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        # Consensus Energy (Avg abs move in bps)
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("macro_energy")
    ])
    
    # 2. Paradox Parameters
    ENERGY_MIN = 2.0 / 10000       # High Force
    NSX_STALL = 0.1 / 10000        # Perfect Stillness
    CONSENSUS_GO = 7               # Unanimous Lead
    SPREAD = 1.5                   # Broker friction
    
    # 3. Signals
    df = df.with_columns([
        (
            (pl.col("consensus_up") >= CONSENSUS_GO) & 
            (pl.col("macro_energy") > ENERGY_MIN) & 
            (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)
        ).alias("signal_long"),
        (
            (pl.col("consensus_down") >= CONSENSUS_GO) & 
            (pl.col("macro_energy") > ENERGY_MIN) & 
            (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)
        ).alias("signal_short")
    ])
    
    # 4. Evaluation (15m horizon)
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - SPREAD)
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - SPREAD)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pnl_bps") != 0)
    
    print(f"\n>>> PARADOX SENTINEL RESULTS: {dataset_path} <<<")
    if len(results) > 0:
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps (NET)")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        print(f"  Gross Alpha:  {results['pnl_bps'].mean() + SPREAD:.3f} bps")
    else:
        print("  No paradox events detected.")

if __name__ == "__main__":
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["graph_dataset_1m_2025.parquet"]
    for p in paths:
        run_paradox_sentinel(p)
