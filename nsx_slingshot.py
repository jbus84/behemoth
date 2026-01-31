import polars as pl
import numpy as np
import os

def run_nsx_slingshot(dataset_path):
    if not os.path.exists(dataset_path):
        print(f"Dataset {dataset_path} missing.")
        return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Base Metrics
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol")
    ])
    
    # 2. Strategy: The Slingshot
    CONSENSUS_GO = 7
    DIVERGENCE_MIN = 0.5 / 10000 
    
    df = df.with_columns(
        (pl.col("hour_utc").is_between(12, 20)).alias("trade_window") 
    )
    
    df = df.with_columns([
        (pl.col("trade_window") & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") < -DIVERGENCE_MIN)).alias("long_slingshot"),
        (pl.col("trade_window") & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") > DIVERGENCE_MIN)).alias("short_slingshot")
    ])
    
    # 3. Evaluation (15m horizon)
    df = df.with_columns(
        (pl.when(pl.col("long_slingshot")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("short_slingshot")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pnl_bps") != 0)
    
    print(f"\n>>> RESULTS FOR {dataset_path} <<<")
    if len(results) > 0:
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No slingshot divergence detected.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            run_nsx_slingshot(path)
    else:
        run_nsx_slingshot("graph_dataset_1m_2025.parquet")
