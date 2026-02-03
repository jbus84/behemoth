
import polars as pl
import os
import glob
import gc

SOURCE_DIR = "/Users/danielfisher/Desktop/tick"
TARGET_DIR = "data/global_15m"

def build_all_15m():
    print("--- BUILDING GLOBAL 15M DATASET (STREAMING) ---")
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    assets = [d for d in os.listdir(SOURCE_DIR) if os.path.isdir(os.path.join(SOURCE_DIR, d))]
    print(f"Found {len(assets)} assets.")
    
    for asset in assets:
        asset_dir = os.path.join(SOURCE_DIR, asset)
        target_path = os.path.join(TARGET_DIR, f"{asset}_15m.parquet")
        
        if os.path.exists(target_path):
            print(f"Skipping {asset}: Already exists.")
            continue
            
        # Scan for Parquet
        files = glob.glob(os.path.join(asset_dir, "*_ticks.parquet"))
        if not files:
            print(f"Skipping {asset}: No *_ticks.parquet files found.")
            continue
            
        # Sort files to ensure time locality for streaming
        files.sort()
        print(f"Processing {asset} ({len(files)} files)...")
        
        try:
            q = pl.scan_parquet(files)
            
            # Aggregations
            # Group by 15m
            q_15m = q.sort("timestamp").group_by_dynamic("timestamp", every="15m").agg([
                pl.col("bid").last().alias(f"close_{asset}"),
                pl.col("ask").last().alias(f"ask_{asset}"),
                (pl.col("ask").mean() - pl.col("bid").mean()).alias(f"spread_{asset}")
            ])
            
            # Use sink_parquet for Streaming
            q_15m.sink_parquet(target_path)
            
            print(f"Saved {target_path} (Streamed)")
            
            # Cleanup
            del q, q_15m
            gc.collect()
            
        except Exception as e:
            print(f"Error processing {asset}: {e}")

if __name__ == "__main__":
    build_all_15m()
