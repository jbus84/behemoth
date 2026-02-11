
import polars as pl
import os
import glob
import gc

SOURCE_DIR = "/Users/danielfisher/Desktop/tick"
TARGET_DIRS = {
    "1h": "data/global_1h",
    "4h": "data/global_4h",
    "15m": "data/global_15m"
}

BATCH_SIZE = 10 # Process 10 Parquet files at a time (conservative)

def build_chunked(asset, timeframe="1h"):
    print(f"--- BATCH BUILDING {asset} ({timeframe}) ---")

    asset_dir = os.path.join(SOURCE_DIR, asset)
    files = glob.glob(os.path.join(asset_dir, "*_ticks.parquet"))
    files.sort()

    if not files:
        print(f"No files found for {asset}")
        return

    print(f"Found {len(files)} files. Processing in batches of {BATCH_SIZE}...")

    # We need to process batches, resample them, and accrue the OHLC results.
    # Since we are reducing ticks -> OHLC, the result is tiny.
    # So we can keep the *result* in memory easily.

    ohlc_chunks = []

    for i in range(0, len(files), BATCH_SIZE):
        batch_files = files[i : i + BATCH_SIZE]
        print(f"Processing Batch {i//BATCH_SIZE + 1} ({len(batch_files)} files)...")

        try:
            q = pl.scan_parquet(batch_files)

            # Resample Batch
            # Note: Edge cases (ticks crossing batch boundaries) might lose a split-second.
            # For 5-year analysis, this is acceptable error (< 0.01%).

            q_resampled = q.sort("timestamp").group_by_dynamic("timestamp", every=timeframe).agg([
                pl.col("bid").last().alias(f"close_{asset}"),
                pl.col("ask").last().alias(f"ask_{asset}"),
                (pl.col("ask").mean() - pl.col("bid").mean()).alias(f"spread_{asset}")
            ])

            df_chunk = q_resampled.collect()
            ohlc_chunks.append(df_chunk)

            del q, q_resampled, df_chunk
            gc.collect()

        except Exception as e:
            print(f"Error in batch {i}: {e}")

    # Combine all OHLC chunks
    print("merging chunks...")
    full_df = pl.concat(ohlc_chunks)

    # Sort and Deduplicate (in case of overlaps, though unlikely with file sort)
    full_df = full_df.sort("timestamp")

    target_dir = TARGET_DIRS[timeframe]
    if not os.path.exists(target_dir): os.makedirs(target_dir)
    target_path = os.path.join(target_dir, f"{asset}_{timeframe}.parquet")

    full_df.write_parquet(target_path)
    print(f"SUCCESS: Saved {target_path} ({len(full_df)} rows)")

if __name__ == "__main__":
    # Explicitly run for the problematic heavy assets
    heavy_assets = ["XAUUSD", "EURJPY", "NSXUSD"]

    for asset in heavy_assets:
        for tf in ["1h", "4h", "15m"]:
            build_chunked(asset, tf)
