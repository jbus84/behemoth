import polars as pl
import os
from pathlib import Path
import argparse
import datetime
import numpy as np

def extract_patterns(idx_path, fx_root, ym="202512", burst_threshold_bps=2.0, forward_sec=30):
    root = Path(fx_root)
    idx_name = Path(idx_path).parent.name
    print(f"Extracting patterns for {idx_name} vs FX Universe...")
    
    if not idx_path.exists():
        print(f"Index data not found: {idx_path}")
        return
        
    # Load Index
    idx = pl.read_parquet(idx_path).select(["timestamp", "mid", "ask", "bid"]).sort("timestamp")
    idx = idx.with_columns(((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10000).alias("spread"))
    
    all_data = []
    
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    
    for fx_name in fx_pairs:
        fx_path = root / fx_name / f"{fx_name}_{ym}_ticks.parquet"
        if not fx_path.exists(): continue
        
        print(f"  Processing {fx_name}...")
        fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
        
        # Resample to 1s for alignment
        start = max(idx["timestamp"].min(), fx["timestamp"].min())
        end = min(idx["timestamp"].max(), fx["timestamp"].max())
        grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").with_columns(
            pl.col("timestamp").dt.cast_time_unit("ns")
        ).sort("timestamp")
        
        combined = grid.join_asof(idx, on="timestamp", strategy="backward")
        combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
        
        # Features
        combined = combined.with_columns([
            (((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000).alias("fx_ret_5s"),
            (pl.col("mid").pct_change().rolling_std(window_size=30) * 10000).alias("idx_vol_30s"),
            pl.col("timestamp").dt.hour().alias("hour"),
            pl.col("timestamp").dt.minute().alias("minute")
        ])
        
        # Detect Bursts
        bursts = combined.filter(pl.col("fx_ret_5s").abs() >= burst_threshold_bps)
        
        if len(bursts) == 0: continue
        
        # Target: Forward Return at 30s
        targets = bursts.select(["timestamp", "mid", "fx_ret_5s", "idx_vol_30s", "spread", "hour", "minute"]).with_columns(
            (pl.col("timestamp") + datetime.timedelta(seconds=forward_sec)).alias("target_time")
        ).with_columns(pl.col("target_time").dt.cast_time_unit("ns"))
        
        labels = targets.join_asof(
            combined.select(["timestamp", "mid"]).rename({"mid": "mid_after"}),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        labels = labels.with_columns([
            (((pl.col("mid_after") / pl.col("mid")) - 1) * 10000).alias("fwd_ret_bps"),
            pl.lit(fx_name).alias("fx_pair")
        ])
        
        # Binary target: 1 if index follows the burst direction, 0 otherwise
        labels = labels.with_columns(
            ((pl.col("fwd_ret_bps") * pl.col("fx_ret_5s").sign()) > 0).cast(pl.Int8).alias("target")
        ).drop_nulls()
        
        all_data.append(labels.drop(["mid", "mid_after", "target_time"]))
        
    if not all_data:
        print(f"No patterns found for {idx_name}.")
        return
        
    final_df = pl.concat(all_data)
    output_path = Path(f"lead_lag_patterns_{idx_name}.parquet")
    final_df.write_parquet(output_path)
    print(f"Extracted {len(final_df)} patterns to {output_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idx_root", type=str, required=True)
    parser.add_argument("--fx_root", type=str, required=True)
    args = parser.parse_args()
    
    indices = ["NSXUSD", "SPXUSD"]
    for idx_folder in indices:
        idx_path = Path(args.idx_root) / idx_folder / f"{idx_folder}_202512_ticks.parquet"
        extract_patterns(idx_path, args.fx_root)

if __name__ == "__main__":
    main()
