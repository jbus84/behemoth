import polars as pl
import os
from pathlib import Path
import glob

def analyze_index(index_path):
    index_name = index_path.name
    # Find the most recent parquet file
    files = glob.glob(str(index_path / f"{index_name}_*_ticks.parquet"))
    if not files:
        return None
    
    # Sort files to find the latest
    files.sort()
    parquet_file = Path(files[-1])
    
    try:
        df = pl.read_parquet(parquet_file)
    except Exception as e:
        print(f"Error reading {parquet_file}: {e}")
        return None
    
    # Basic Metrics
    avg_spread = df["spread"].mean()
    avg_price = df["mid"].mean()
    
    # Calculate ticks per hour (Volume proxy)
    first_time = df["timestamp"].min()
    last_time = df["timestamp"].max()
    duration_hours = (last_time - first_time).total_seconds() / 3600
    
    # Filter for active trading hours (e.g., skip weekends/holidays if any in the file)
    # Just a simple count/hours for now
    ticks_per_hour = len(df) / duration_hours if duration_hours > 0 else 0
    
    # Volatility
    df = df.with_columns(
        date=pl.col("timestamp").dt.date()
    )
    daily_stats = df.group_by("date").agg([
        pl.col("mid").max().alias("high"),
        pl.col("mid").min().alias("low")
    ])
    daily_stats = daily_stats.with_columns(
        range=pl.col("high") - pl.col("low")
    )
    avg_daily_range = daily_stats["range"].mean()
    
    # Spread/Range Ratio
    spread_to_range_ratio = (avg_spread / avg_daily_range) * 100 if avg_daily_range > 0 else 0
    
    return {
        "Index": index_name,
        "Ticks/Hour": ticks_per_hour,
        "Avg Price": avg_price,
        "Avg Spread": avg_spread,
        "Spread/Range %": spread_to_range_ratio
    }

base_path = Path("/Users/danielfisher/Desktop/tick")
index_dirs = [d for d in base_path.iterdir() if d.is_dir()]

results = []
for d in index_dirs:
    res = analyze_index(d)
    if res:
        results.append(res)

if results:
    output_df = pl.DataFrame(results).sort("Ticks/Hour", descending=True)
    print(output_df)
else:
    print("No results found.")
