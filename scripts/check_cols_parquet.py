import polars as pl

f = "data/global_15m/EURUSD_15m.parquet"
try:
    df = pl.read_parquet(f)
    print(f"Columns in {f}: {df.columns}")
    print(df.head())
except Exception as e:
    print(e)
