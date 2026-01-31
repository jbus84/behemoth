import polars as pl
import numpy as np
import os

def run_afternoon_exhaustion():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING THE AFTERNOON EXHAUSTION MODEL (FADING THIN SHOCKS) <<<")
    
    # 1. Base Metrics
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("macro_energy"),
        pl.col("timestamp").dt.hour().alias("hour_utc")
    ])
    
    # 2. Strategy: Thin Market Reversion
    # Window: 19:00 - 21:00 UTC (Post-London, Pre-Close churn)
    # Energy: > 3.0 bps shock
    
    CONSENSUS_GO = 7
    SHOCK_MIN = 3.0 / 10000
    
    df = df.with_columns(
        (pl.col("hour_utc").is_between(19, 21)).alias("thin_window")
    )
    
    df = df.with_columns([
        (pl.col("thin_window") & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("macro_energy") > SHOCK_MIN)).alias("long_fade"),
        (pl.col("thin_window") & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("macro_energy") > SHOCK_MIN)).alias("short_fade")
    ])
    
    # 3. Evaluation (15m horizon)
    # Reversion = Trade Against
    df = df.with_columns(
        (pl.when(pl.col("long_fade")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("short_fade")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pnl_bps") != 0)
    if len(results) > 0:
        print(f"\n>>> AFTERNOON EXHAUSTION RESULTS (FADE MODE) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No extreme afternoon shocks detected.")

if __name__ == "__main__":
    run_afternoon_exhaustion()
