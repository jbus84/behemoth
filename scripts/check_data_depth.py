
import polars as pl
import os

DATA_DIR = "data/global_4h"
files = ["FRXEUR_4h.parquet", "BCOUSD_4h.parquet", "GRXEUR_4h.parquet", "SPXUSD_4h.parquet"]

for f in files:
    p = os.path.join(DATA_DIR, f)
    if os.path.exists(p):
        df = pl.read_parquet(p)
        print(f"{f}: {df['timestamp'].min()} to {df['timestamp'].max()}")
    else:
        print(f"{f}: NOT FOUND")
