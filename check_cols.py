import polars as pl
file_path = "/Users/danielfisher/Desktop/tick/NSXUSD/NSXUSD_202401_ticks.parquet"
df = pl.read_parquet(file_path)
print("--- Columns ---")
print(df.columns)
print("--- Head ---")
print(df.head(5))
