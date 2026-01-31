import polars as pl
import os
from pathlib import Path
import datetime

def analyze_reverse_lead(idx_name, tick_root, ym="202512"):
    print(f"\n>>> TESTING REVERSE LEAD: {idx_name} -> FX ({ym}) <<<")
    
    idx_path = Path(tick_root) / idx_name / f"{idx_name}_{ym}_ticks.parquet"
    if not idx_path.exists():
        print(f"Index data missing: {idx_path}")
        return

    # Load Index
    idx = pl.read_parquet(idx_path).select(["timestamp", "mid"]).rename({"mid": "idx_px"}).sort("timestamp")
    
    # Calculate Index Bursts (e.g., > 5bps move in 5s)
    idx = idx.with_columns(
        (((pl.col("idx_px") / pl.col("idx_px").shift(5)) - 1) * 10000).alias("idx_ret_5s")
    )
    
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    
    for fx_name in fx_pairs:
        fx_path = Path(tick_root) / fx_name / f"{fx_name}_{ym}_ticks.parquet"
        if not fx_path.exists(): continue
        
        fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
        
        # Resample to 1s
        start = max(idx["timestamp"].min(), fx["timestamp"].min())
        end = min(idx["timestamp"].max(), fx["timestamp"].max())
        grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").sort("timestamp")
        
        combined = grid.join_asof(idx, on="timestamp", strategy="backward")
        combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
        
        # Trigger: Index Burst > 5bps
        bursts = combined.filter(pl.col("idx_ret_5s").abs() >= 5.0)
        
        if len(bursts) == 0: continue
        
        # Target: FX Return 30s Later
        targets = bursts.select(["timestamp", "idx_ret_5s", "fx_px"]).with_columns(
            (pl.col("timestamp") + datetime.timedelta(seconds=30)).alias("target_time")
        )
        
        labels = targets.join_asof(
            combined.select(["timestamp", "fx_px"]).rename({"fx_px": "fx_after"}),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        labels = labels.with_columns(
            (((pl.col("fx_after") / pl.col("fx_px")) - 1) * 10000).alias("fx_fwd_ret")
        ).drop_nulls()
        
        # Did FX Follow? (Correlation)
        labels = labels.with_columns(
            ((pl.col("fx_fwd_ret") * pl.col("idx_ret_5s").sign()) > 0).cast(pl.Int8).alias("is_trend")
        )
        
        trend_prob = labels["is_trend"].mean() * 100
        revert_prob = 100 - trend_prob
        avg_move = labels["fx_fwd_ret"].abs().mean()
        
        print(f"Index -> {fx_name}:")
        print(f"  Follow Probability: {trend_prob:.1f}%")
        print(f"  Revert Probability: {revert_prob:.1f}%")
        print(f"  Avg FX Response:    {avg_move:.3f} bps")

def main():
    tick_root = "/Users/danielfisher/Desktop/tick"
    analyze_reverse_lead("NSXUSD", tick_root)

if __name__ == "__main__":
    main()
