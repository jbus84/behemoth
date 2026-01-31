import polars as pl
import numpy as np
import os

def run_macro_vol_pulse():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    target = 'USDJPY'
    anchors = [n for n in nodes if n != target]
    
    print(f">>> RUNNING MACRO VOL PULSE (TARGET: {target}) <<<")
    
    # 1. Intensity Metrics
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        # Total ENERGY in the anchors
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("macro_energy")
    ])
    
    # 2. Strategy: High-Energy Trend Following
    # Consensus 7/8 AND Macro Energy > 2.0 BPS (A real shock)
    CONSENSUS_GO = 7
    ENERGY_MIN = 2.5 / 10000 
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("macro_energy") > ENERGY_MIN)).alias("long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("macro_energy") > ENERGY_MIN)).alias("short")
    ])
    
    # 3. Evaluation (15m)
    # USDJPY spread = 0.5
    df = df.with_columns(
        (pl.when(pl.col("long")).then( (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 0.5)
          .when(pl.col("short")).then(-(pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()) * 10000 - 0.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("long") | pl.col("short"))
    if len(results) > 0:
        print(f"\n>>> MACRO VOL PULSE RESULTS (OOS 2025) <<<")
        print(f"  Target:       {target}")
        print(f"  Energy Thr:   {ENERGY_MIN*10000:.2f} bps")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")

if __name__ == "__main__":
    run_macro_vol_pulse()
