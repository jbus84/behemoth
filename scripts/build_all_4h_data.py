
import polars as pl
import os
import glob
import gc

SOURCE_DIR = "/Users/danielfisher/Desktop/tick"
TARGET_DIR = "data/global_4h"

def build_all_4h():
    print("--- BUILDING GLOBAL 4H DATASET (FROM PARQUET) ---")
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)

    assets = [d for d in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, d))]
    print(f"Found {len(assets)} assets.")

    for asset in assets:
        asset_dir = os.path.join(SOURCE_DIR, asset)
        target_path = os.path.join(TARGET_DIR, f"{asset}_4h.parquet")

        if os.path.exists(target_path):
            print(f"Skipping {asset}: Already exists.")
            continue

        # Scan for Parquet
        files = glob.glob(os.path.join(asset_dir, "*_ticks.parquet"))
        if not files:
            print(f"Skipping {asset}: No *_ticks.parquet files found.")
            continue

        files.sort() # Ensure time order layout
        print(f"Processing {asset} ({len(files)} files)...")

        try:
            # We can skip Gold/Silver if they crashed before?
            # Or just let them crash and touch skipping file.
            # 1H builder failed on XAUUSD, EURJPY.
            # I will preemptively skip them if they are too big?
            # Or try to run. 4H aggregation reduces data massively, so result is small.
            # But the LOAD phase is the bottleneck (loading 193 files).
            # Lazy scan handles this well usually.

            q = pl.scan_parquet(files)

            # Aggregations
            # Streaming requires careful handling of sort
            # We sort files first to help locality

            q_4h = q.sort("timestamp").group_by_dynamic("timestamp", every="4h").agg([
                pl.col("bid").last().alias(f"close_{asset}"),
                pl.col("ask").last().alias(f"ask_{asset}"),
                (pl.col("ask").mean() - pl.col("bid").mean()).alias(f"spread_{asset}")
            ])

            # Use sink_parquet for True Streaming (Low RAM)
            # Maintain order must be False for streaming usually, but we need time order?
            # Actually group_by_dynamic output is time-keyed.
            q_4h.sink_parquet(target_path)

            print(f"Saved {target_path} (Streamed)")

            # Cleanup
            del q, q_4h
            gc.collect()

        except Exception as e:
            print(f"Error processing {asset}: {e}")

if __name__ == "__main__":
    build_all_4h()
