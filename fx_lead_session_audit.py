import polars as pl
import numpy as np
import os

def run_session_audit(dataset_path):
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Re-calculate 7/8 Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    CONSENSUS_GO = 7
    NSX_MAX_MOVE = 0.2 / 10000
    
    df = df.with_columns([
        ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("signal_long"),
        ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_MAX_MOVE)).alias("signal_short")
    ])
    
    # Eval
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(None)).alias("pnl_bps")
    )
    
    # Add Session Info
    df = df.with_columns(
        pl.col("timestamp").dt.hour().alias("hour_utc")
    )
    
    # 2. Audit by Hour
    pl.Config.set_tbl_rows(100)
    hour_stats = df.filter(pl.col("pnl_bps").is_not_null()).group_by("hour_utc").agg([
        pl.count("pnl_bps").alias("trades"),
        (pl.col("pnl_bps") > 0).mean().alias("win_rate"),
        pl.col("pnl_bps").mean().alias("avg_pnl")
    ]).sort("hour_utc")
    
    print("\n>>> SESSION AUDIT: 7/8 CONSENSUS BY HOUR (UTC) <<<")
    print(hour_stats)
    
    # 3. Audit by Volatility Range
    df = df.with_columns(
        pl.col("NSXUSD_vol_30m").round(0).alias("vol_bucket")
    )
    
    vol_stats = df.filter(pl.col("pnl_bps").is_not_null()).group_by("vol_bucket").agg([
        pl.count("pnl_bps").alias("trades"),
        (pl.col("pnl_bps") > 0).mean().alias("win_rate"),
        pl.col("pnl_bps").mean().alias("avg_pnl")
    ]).sort("vol_bucket")
    
    print(f"\n>>> REGIME AUDIT FOR {dataset_path} <<<")
    print(vol_stats)

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_session_audit(f"graph_dataset_1m_{y}.parquet")
