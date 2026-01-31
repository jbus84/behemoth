import polars as pl
import os
from pathlib import Path
import argparse
import numpy as np

def analyze_persistence(parquet_path, windows_sec=[5, 10, 30, 60, 300, 600, 1800, 3600]):
    print(f"Loading data from {parquet_path}...")
    df = pl.read_parquet(parquet_path).sort("timestamp")
    
    results = []
    
    # We use log returns to measure persistence
    # Resample to common time grids to calculate autocorrelation
    for window in windows_sec:
        # Resample to 'window' seconds
        # mid.last() gives the closing price for each bin
        resampled = df.group_by_dynamic(
            "timestamp", 
            every=f"{window}s"
        ).agg(pl.col("mid").last().alias("price"))
        
        # Calculate log returns
        resampled = resampled.with_columns(
            log_ret=(pl.col("price").log() - pl.col("price").log().shift(1)).fill_null(0)
        )
        
        # Calculate Autocorrelation (Lag 1)
        # If corr > 0: Trend persists
        # If corr < 0: Mean reversion (Anti-persistence)
        if len(resampled) > 2:
            corr = resampled.select(
                pl.corr("log_ret", pl.col("log_ret").shift(1))
            ).to_series()[0]
            
            results.append({
                "Horizon": f"{window}s",
                "Autocorrelation": round(corr, 4),
                "Regime": "Trending" if corr > 0.05 else ("Mean Reverting" if corr < -0.05 else "Random Walk")
            })
            
    print(f"\n--- Nasdaq Trend Persistence Analysis ({Path(parquet_path).name}) ---")
    print(pl.DataFrame(results))
    print("\nNote: Autocorrelation measures how much the next move depends on the current one.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    args = parser.parse_args()
    
    analyze_persistence(args.input)
