import polars as pl
import numpy as np
import os

def run_surgical_sentinel(dataset_path):
    if not os.path.exists(dataset_path):
        print(f"Dataset {dataset_path} missing.")
        return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Consensus Logic
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    # 2. Filters from Audit
    df = df.with_columns([
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol")
    ])
    
    CONSENSUS_GO = 7
    NSX_MAX_MOVE = 0.2 / 10000
    
    # Surgical Gating
    df = df.with_columns(
        (
            (pl.col("hour_utc").is_between(14, 19)) & 
            ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0))
        ).alias("market_fit")
    )
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE) & pl.col("market_fit")).alias("signal_long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE) & pl.col("market_fit")).alias("signal_short")
    ])
    
    # 3. Evaluation
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
    
    print(f"\n>>> RESULTS FOR {dataset_path} <<<")
    if len(results) > 0:
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
    else:
        print("No surgical signals detected.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            run_surgical_sentinel(path)
    else:
        run_surgical_sentinel("graph_dataset_1m_2025.parquet")
