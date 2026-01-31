import polars as pl
import os
from pathlib import Path
import glob

def get_latest_file(index_path):
    index_name = index_path.name
    files = glob.glob(str(index_path / f"{index_name}_*_ticks.parquet"))
    if not files:
        return None
    files.sort()
    return Path(files[-1])

def load_index_returns(index_path):
    f = get_latest_file(index_path)
    if not f:
        return None
    
    df = pl.read_parquet(f)
    # Resample to 1-minute mid prices
    # We take the last mid price of each minute
    df = df.with_columns(
        minute=pl.col("timestamp").dt.truncate("1m")
    ).group_by("minute").agg(
        pl.col("mid").last().alias(index_path.name)
    ).sort("minute")
    
    return df

base_path = Path("/Users/danielfisher/Desktop/tick")
indices_to_compare = ["SPXUSD", "NSXUSD", "GRXEUR", "JPXJPY", "HKXHKD", "UKXGBP", "FRXEUR"]

combined_df = None

for idx in indices_to_compare:
    idx_df = load_index_returns(base_path / idx)
    if idx_df is not None:
        if combined_df is None:
            combined_df = idx_df
        else:
            combined_df = combined_df.join(idx_df, on="minute", how="inner")

if combined_df is not None:
    # Calculate log returns
    returns_cols = []
    for idx in indices_to_compare:
        if idx in combined_df.columns:
            combined_df = combined_df.with_columns(
                (pl.col(idx).log().diff()).alias(f"{idx}_ret")
            )
            returns_cols.append(f"{idx}_ret")
    
    # Drop first row (NaN from diff)
    returns_df = combined_df.select(returns_cols).drop_nulls()
    
    # Calculate correlation matrix
    corr_matrix = returns_df.corr()
    
    # Print it nicely
    print("Index Correlation Matrix (1-minute log returns):")
    print(corr_matrix)
else:
    print("No overlapping data found for correlation analysis.")
