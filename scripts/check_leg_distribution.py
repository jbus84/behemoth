
import polars as pl
import numpy as np

try:
    df = pl.read_csv("data/events/events_m5_8yr_v3_mom.csv")
    print("--- Leg Distribution ---")
    print(df["active_leg"].value_counts())
    
    print("\n--- PnL by Leg ---")
    print(df.group_by("active_leg").agg([
        pl.col("pnl_bps").mean().alias("mean_pnl"),
        pl.col("pnl_bps").count().alias("count"),
        pl.col("pnl_bps").sum().alias("total_pnl")
    ]))

    # Check beta if available? Not in CSV explicitly, but we have side/strategy.
except Exception as e:
    print(f"Error reading CSV: {e}")
