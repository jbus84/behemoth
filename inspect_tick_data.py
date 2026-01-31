import polars as pl
import os

# Inspect a sample tick file
# Path provided by user: /Users/danielfisher/Desktop/tick
# File discovered: NSXUSD/NSXUSD_202401_ticks.parquet

file_path = "/Users/danielfisher/Desktop/tick/NSXUSD/NSXUSD_202401_ticks.parquet"

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
    # Try a different one if 202401 missing (though it was in the list)
    exit(1)

print(f"Loading {file_path}...")
df = pl.read_parquet(file_path)

print("\n--- Schema ---")
print(df.schema)

print("\n--- First 10 Rows ---")
print(df.head(10))

print("\n--- Timestamp Resolution Check ---")
ts_sample = df["timestamp"][0]
print(f"Sample TS: {ts_sample}")
print(f"Dtype: {df['timestamp'].dtype}")

# Check for Bid/Ask columns
required = ["bid", "ask", "bid_vol", "ask_vol"]
missing = [c for c in required if c not in df.columns]

if missing:
    print(f"\nWARNING: Missing columns: {missing}")
else:
    print("\nSUCCESS: All Order Book columns present.")

# Check for gaps (just a quick delta check)
df = df.sort("timestamp")
deltas = df["timestamp"].diff().drop_nulls().dt.total_milliseconds()
print(f"\n--- Time Deltas (ms) ---")
print(deltas.describe())
