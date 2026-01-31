import polars as pl
import os

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/swing"

def inspect():
    path = os.path.join(DATA_DIR, "NSXUSD_1d.parquet")
    if not os.path.exists(path):
        print("File not found.")
        return

    df = pl.read_parquet(path)
    print(f"Loaded {len(df)} rows.")
    print("--- Head ---")
    print(df.head(5))
    print("--- Tail ---")
    print(df.tail(5))
    
    # Check distinct dates
    print(f"Unique Timestamps: {df['timestamp'].n_unique()}")
    
    # Check date range
    print(f"Min Date: {df['timestamp'].min()}")
    print(f"Max Date: {df['timestamp'].max()}")

if __name__ == "__main__":
    inspect()
