
import polars as pl
import os

DATA_DIR = "data/global_1h"
pair = ("FRXEUR", "BCOUSD")

p_y = os.path.join(DATA_DIR, f"{pair[0]}_1h.parquet")
p_x = os.path.join(DATA_DIR, f"{pair[1]}_1h.parquet")

if os.path.exists(p_y) and os.path.exists(p_x):
    df = pl.read_parquet(p_y)
    print(f"{pair[0]}_1h: {df['timestamp'].min()} to {df['timestamp'].max()}")
else:
    print(f"Missing H1 data for {pair}")
