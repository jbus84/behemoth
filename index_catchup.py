import polars as pl
import numpy as np
import os

def run_index_catchup():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    # Leaders: SPX + the 6 FX anchors
    leaders = ['SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
    target = 'NSXUSD'
    
    print(">>> RUNNING THE INDEX CATCH-UP MODEL (SPX + FX LEAD) <<<")
    
    # 1. Leadership Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in leaders]).alias("leader_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in leaders]).alias("leader_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol")
    ])
    
    # 2. Strict Lead Logic
    # 6 out of 7 leaders must move (including SPX)
    LEADER_GO = 6
    NSX_STALLED = 0.1 / 10000 # Near zero movement
    
    df = df.with_columns(
        ((pl.col("hour_utc") == 14) | (pl.col("hour_utc") == 15)).alias("open_window"),
        ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0)).alias("vol_fit")
    ).with_columns([
        (pl.col("open_window") & pl.col("vol_fit") & (pl.col("leader_up") >= LEADER_GO) & (pl.col("SPXUSD_ret_1m") > 0) & (pl.col(f"{target}_ret_1m").abs() < NSX_STALLED)).alias("long"),
        (pl.col("open_window") & pl.col("vol_fit") & (pl.col("leader_down") >= LEADER_GO) & (pl.col("SPXUSD_ret_1m") < 0) & (pl.col(f"{target}_ret_1m").abs() < NSX_STALLED)).alias("short")
    ])
    
    # 3. Evaluation
    df = df.with_columns(
        (pl.when(pl.col("long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pnl_bps") != 0)
    if len(results) > 0:
        print(f"\n>>> INDEX CATCH-UP RESULTS (US OPEN) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")

if __name__ == "__main__":
    run_index_catchup()
