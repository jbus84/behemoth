
import os
import polars as pl

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/global_1h"

try:
    if not os.path.exists(DATA_DIR):
        print(f"Directory not found: {DATA_DIR}")
    else:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith("_1h.parquet")]
        print(f"Found {len(files)} files.")
        if files:
            print(f"Sample: {files[0]}")
            df = pl.read_parquet(os.path.join(DATA_DIR, files[0]))
            print(f"Columns: {df.columns}")
            print(f"Rows: {len(df)}")
except Exception as e:
    print(f"Error: {e}")
