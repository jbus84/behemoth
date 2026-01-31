import polars as pl
import os
from pathlib import Path
import datetime

def extract_full_year_features(idx_name, tick_root):
    print(f"\n>>> EXTRACTING REGIME FEATURES FOR {idx_name} (FULL YEAR 2025) <<<")
    
    months = [f"2025{m:02d}" for m in range(1, 13)]
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    all_chunks = []
    
    tick_root = Path(tick_root)
    
    for ym in months:
        idx_path = tick_root / idx_name / f"{idx_name}_{ym}_ticks.parquet"
        if not idx_path.exists(): continue
        
        print(f"  Processing {ym}...")
        try:
            # Load Index
            idx = pl.read_parquet(idx_path).select(["timestamp", "mid", "ask", "bid"]).sort("timestamp")
            idx = idx.with_columns(((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10000).alias("spread"))
            
            # Pre-calculate Index Returns for Correlation
            # We use 1s returns for correlation calculation
            idx = idx.with_columns(
                pl.col("mid").pct_change().alias("idx_ret")
            )

            for fx_name in fx_pairs:
                fx_path = tick_root / fx_name / f"{fx_name}_{ym}_ticks.parquet"
                if not fx_path.exists(): continue
                
                fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
                
                # Align to 1s Grid
                start = max(idx["timestamp"].min(), fx["timestamp"].min())
                end = min(idx["timestamp"].max(), fx["timestamp"].max())
                grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").with_columns(
                    pl.col("timestamp").dt.cast_time_unit("ns")
                ).sort("timestamp")
                
                combined = grid.join_asof(idx, on="timestamp", strategy="backward")
                combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
                
                # Calculate FX Returns
                combined = combined.with_columns(
                    pl.col("fx_px").pct_change().alias("fx_ret")
                )
                
                # --- NEW: REGIME FEATURES ---
                # Rolling Correlation (60-minute window = 3600 seconds)
                # Pearson Correlation between FX returns and Index returns
                combined = combined.with_columns([
                    pl.rolling_corr("fx_ret", "idx_ret", window_size=3600).alias("regime_corr_1h")
                ]).fill_null(0) # First hour will be null/0
                
                # Standard Features for Burst Detection
                combined = combined.with_columns([
                    (((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000).alias("fx_ret_5s"),
                    (pl.col("mid").pct_change().rolling_std(window_size=30) * 10000).alias("idx_vol_30s"),
                    (((pl.col("mid") / pl.col("mid").shift(5)) - 1) * 10000).alias("idx_ret_5s"),
                    (pl.col("spread") - pl.col("spread").shift(60)).alias("spread_chg_60s"),
                    pl.col("timestamp").dt.hour().alias("hour"),
                ])
                
                # Filter for Bursts (Trigger)
                bursts = combined.filter(pl.col("fx_ret_5s").abs() >= 2.0)
                if len(bursts) == 0: continue
                
                # Target: 30s Forward Direction (Signal Horizon)
                targets = bursts.select(["timestamp", "mid", "fx_ret_5s", "idx_vol_30s", "spread", "hour", "regime_corr_1h", "idx_ret_5s", "spread_chg_60s"]).with_columns(
                    (pl.col("timestamp") + datetime.timedelta(seconds=30)).alias("target_time")
                ).with_columns(pl.col("target_time").dt.cast_time_unit("ns"))
                
                labels = targets.join_asof(
                    combined.select(["timestamp", "mid"]).rename({"mid": "mid_after"}),
                    left_on="target_time",
                    right_on="timestamp",
                    strategy="forward"
                )
                
                # Label: 1 if Trend-Follow (Same Sign), 0 if Revert (Opposite Sign)
                labels = labels.with_columns([
                    (((pl.col("mid_after") / pl.col("mid")) - 1) * 10000).alias("fwd_ret_bps"),
                    pl.lit(fx_name).alias("fx_pair")
                ])
                
                labels = labels.with_columns(
                    ((pl.col("fwd_ret_bps") * pl.col("fx_ret_5s").sign()) > 0).cast(pl.Int8).alias("target_trend")
                ).drop_nulls()
                
                all_chunks.append(labels.drop(["mid", "mid_after", "target_time"]))
                
        except Exception as e:
            print(f"    Error processing {ym}: {e}")
            continue

    if all_chunks:
        final_df = pl.concat(all_chunks)
        output_file = f"full_year_dataset_{idx_name}.parquet"
        final_df.write_parquet(output_file)
        print(f"Saved {len(final_df)} samples to {output_file}")
    else:
        print("No data extracted.")

def main():
    tick_root = "/Users/danielfisher/Desktop/tick"
    # Focusing on Nasdaq as primary lead-lag candidate
    extract_full_year_features("NSXUSD", tick_root)

if __name__ == "__main__":
    main()
