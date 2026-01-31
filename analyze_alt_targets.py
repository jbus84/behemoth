import polars as pl
import os
from pathlib import Path
import datetime

def analyze_alt_targets(idx_name, tick_root, ym="202512"):
    print(f"\n>>> TESTING ALTERNATIVE TARGETS: FX -> {idx_name} Vol/Spread ({ym}) <<<")
    
    idx_path = Path(tick_root) / idx_name / f"{idx_name}_{ym}_ticks.parquet"
    if not idx_path.exists():
        print(f"Index data missing: {idx_path}")
        return

    # Load Index
    idx = pl.read_parquet(idx_path).select(["timestamp", "mid", "ask", "bid"]).sort("timestamp")
    
    # Calculate Spread and Future Volatility
    idx = idx.with_columns([
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10000).alias("spread"),
        # Future Volatility (Std Dev of next 60s) would be hard to calculate efficiently on ticks without lookahead rolling
        # Instead, we'll use Forward Return Magnitude as a proxy for "Realized Volatility"
    ])
    
    # We'll rely on the extract_full logic style
    fx_pairs = ["GBPUSD", "USDJPY"] # Top predictors
    
    for fx_name in fx_pairs:
        fx_path = Path(tick_root) / fx_name / f"{fx_name}_{ym}_ticks.parquet"
        if not fx_path.exists(): continue
        
        fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
        
        # Resample to 1s
        start = max(idx["timestamp"].min(), fx["timestamp"].min())
        end = min(idx["timestamp"].max(), fx["timestamp"].max())
        grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").with_columns(
            pl.col("timestamp").dt.cast_time_unit("ns") # Ensure matching type
        ).sort("timestamp")
        
        # Join
        combined = grid.join_asof(idx, on="timestamp", strategy="backward")
        combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
        
        # Calculate FX Burst (5s)
        combined = combined.with_columns(
             (((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000).alias("fx_ret_5s")
        )
        
        # Filter for Bursts
        bursts = combined.filter(pl.col("fx_ret_5s").abs() >= 2.0)
        
        if len(bursts) == 0: continue
        
        # Target: Future State 60s later
        targets = bursts.select(["timestamp", "fx_ret_5s", "mid", "spread"]).with_columns(
            (pl.col("timestamp") + datetime.timedelta(seconds=60)).alias("target_time")
        ).with_columns(pl.col("target_time").dt.cast_time_unit("ns"))
        
        labels = targets.join_asof(
            combined.select(["timestamp", "mid", "spread"]).rename({"mid": "mid_after", "spread": "spread_after"}),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        # Calculate Metrics
        labels = labels.with_columns([
            # Magnitude of Index Move (Volatility Proxy)
            (((pl.col("mid_after") / pl.col("mid")) - 1) * 10000).abs().alias("idx_move_mag_bps"),
            # Spread Change
            (pl.col("spread_after") - pl.col("spread")).alias("spread_change_bps")
        ]).drop_nulls()
        
        # Baseline (No Burst)
        # Random sample of non-burst times
        baseline_idx_move = 1.2 # Placeholder estimated avg
        baseline_spread = 0.5   # Placeholder
        
        print(f"FX Pair: {fx_name}")
        print(f"  Avg Index Move (60s) after Burst: {labels['idx_move_mag_bps'].mean():.3f} bps")
        print(f"  Avg Spread Change (60s) after Burst: {labels['spread_change_bps'].mean():.3f} bps")
        
        # Correlation between Burst Size and Index Vol
        corr = labels.select(pl.corr("fx_ret_5s", "idx_move_mag_bps")).item(0, 0)
        print(f"  Correlation (Burst Size vs Index Vol): {corr:.3f}")

def main():
    tick_root = "/Users/danielfisher/Desktop/tick"
    analyze_alt_targets("NSXUSD", tick_root)

if __name__ == "__main__":
    main()
