import polars as pl
import os
from pathlib import Path
import glob

def analyze_session_efficiency(index_path, start_hour, end_hour, session_name):
    index_name = index_path.name
    files = glob.glob(str(index_path / f"{index_name}_*_ticks.parquet"))
    if not files:
        return None
    files.sort()
    parquet_file = Path(files[-1])
    
    try:
        df = pl.read_parquet(parquet_file)
    except Exception as e:
        return None
    
    # Filter for session hours (UTC)
    df = df.with_columns(
        hour=pl.col("timestamp").dt.hour()
    ).filter(
        (pl.col("hour") >= start_hour) & (pl.col("hour") < end_hour)
    )
    
    if len(df) == 0:
        return None
    
    avg_spread = df["spread"].mean()
    avg_price = df["mid"].mean()
    
    # Calculate average daily range DURING this session
    df = df.with_columns(
        date=pl.col("timestamp").dt.date()
    )
    session_range = df.group_by("date").agg([
        (pl.col("mid").max() - pl.col("mid").min()).alias("range")
    ])["range"].mean()
    
    # Efficiency = Range / Spread (How many spreads' worth of movement do we get?)
    efficiency = session_range / avg_spread if avg_spread > 0 else 0
    
    return {
        "Index": index_name,
        "Session": session_name,
        "Avg Spread": round(avg_spread, 3),
        "Session Range": round(session_range, 2),
        "Efficiency (Range/Spread)": round(efficiency, 1),
        "Ticks/Hour": round(len(df) / ((end_hour - start_hour) * len(df["date"].unique())), 0)
    }

base_path = Path("/Users/danielfisher/Desktop/tick")

# Define sessions in UTC
# London: 08:00 - 16:30 UTC
# New York: 14:30 - 21:00 UTC
# (Overlap: 14:30 - 16:30)

results = []

# Analyze US Indices during US Hours (14-21 UTC)
for idx in ["SPXUSD", "NSXUSD"]:
    res = analyze_session_efficiency(base_path / idx, 14, 21, "US Session")
    if res: results.append(res)

# Analyze EU Indices during EU Hours (08-16 UTC)
for idx in ["GRXEUR", "FRXEUR", "UKXGBP"]:
    res = analyze_session_efficiency(base_path / idx, 8, 16, "EU Session")
    if res: results.append(res)

# Analyze Asian Indices during Asian Hours (00-08 UTC)
for idx in ["JPXJPY", "HKXHKD"]:
    res = analyze_session_efficiency(base_path / idx, 0, 8, "Asian Session")
    if res: results.append(res)

output_df = pl.DataFrame(results).sort("Efficiency (Range/Spread)", descending=True)
print(output_df)
