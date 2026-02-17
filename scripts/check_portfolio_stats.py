import polars as pl
import sys

f = "data/events/events_h1_8yr_v3_mom.csv"
try:
    df = pl.read_csv(f)
    print(f"Loaded {len(df)} events from {f}")
    
    # Group by Symbol
    stats = df.group_by("symbol").agg([
        pl.count("pnl_bps").alias("trades"),
        pl.sum("pnl_bps").alias("total_pnl"),
        pl.mean("pnl_bps").alias("avg_pnl"),
        (pl.col("pnl_bps") > 0).sum().alias("wins")
    ]).sort("total_pnl", descending=True)
    
    print(stats)
    
    # Portfolio Agg
    total_pnl = df["pnl_bps"].sum()
    total_trades = len(df)
    avg_pnl = total_pnl / total_trades
    print(f"\nTOTAL: {total_trades} trades, {total_pnl:.2f} bps ({avg_pnl:.2f} avg)")

except Exception as e:
    print(e)
