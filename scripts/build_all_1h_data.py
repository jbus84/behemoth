
import polars as pl
import os
import glob
import gc

SOURCE_DIR = "/Users/danielfisher/Desktop/tick"
TARGET_DIR = "data/global_1h"

def build_all_1h():
    print("--- BUILDING GLOBAL 1H DATASET (STREAMING) ---")
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)

    assets = [d for d in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, d))]
    print(f"Found {len(assets)} assets.")

    for asset in assets:
        asset_dir = os.path.join(SOURCE_DIR, asset)
        target_path = os.path.join(TARGET_DIR, f"{asset}_1h.parquet")

        # We manually check if we should skip, but we want to overwrite empties?
        # The script calling this should handle deletion of empties.
        if os.path.exists(target_path):
            print(f"Skipping {asset}: Already exists.")
            continue

        # Scan for Parquet
        files = glob.glob(os.path.join(asset_dir, "*_ticks.parquet"))
        if not files:
            print(f"Skipping {asset}: No *_ticks.parquet files found.")
            continue

        files.sort()
        print(f"Processing {asset} ({len(files)} files)...")

        try:
            q = pl.scan_parquet(files)

            # Aggregations 1H
            q_1h = q.sort("timestamp").group_by_dynamic("timestamp", every="1h").agg([
                pl.col("bid").last().alias(f"close_{asset}"),
                pl.col("ask").last().alias(f"ask_{asset}"),
                (pl.col("ask").mean() - pl.col("bid").mean()).alias(f"spread_{asset}")
            ])

            # Streaming Sink
            q_1h.sink_parquet(target_path)

            print(f"Saved {target_path} (Streamed)")

            # Cleanup
            del q, q_1h
            gc.collect()

        except Exception as e:
            print(f"Error processing {asset}: {e}")

if __name__ == "__main__":
    build_all_1h()
