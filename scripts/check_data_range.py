
import polars as pl
import os

p_xau = "/Users/danielfisher/repositories/behemoth/data/global_4h/XAUUSD_4h.parquet"
if os.path.exists(p_xau):
    df = pl.read_parquet(p_xau)
    print(f"XAUUSD Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
else:
    print("XAUUSD_4h.parquet not found")
