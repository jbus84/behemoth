import polars as pl
import os
from pathlib import Path
import argparse
import numpy as np

def detect_whales(parquet_path, tick_threshold=3, time_ms_threshold=500, z_threshold=2.5, window_size=100):
    print(f"Loading data from {parquet_path}...")
    df = pl.read_parquet(parquet_path)
    
    # 1. Responsive Fair Price (EWMA)
    # Using a fast span to filter noise while staying responsive
    df = df.with_columns(
        fair_price=pl.col("mid").ewm_mean(span=20)
    )
    
    # 2. Activity Bursts (Tick Frequency)
    # Calculate time delta between ticks
    df = df.with_columns(
        time_delta=(pl.col("timestamp").diff().dt.total_milliseconds()).fill_null(0)
    )
    
    # Rolling tick frequency (ticks per second)
    # 1.0 / (rolling mean of time_delta / 1000)
    df = df.with_columns(
        avg_delta=pl.col("time_delta").rolling_mean(window_size=window_size)
    ).with_columns(
        tick_freq=1000.0 / pl.col("avg_delta").replace(0, np.nan)
    )
    
    # Z-Score for frequency
    freq_mean = df["tick_freq"].mean()
    freq_std = df["tick_freq"].std()
    df = df.with_columns(
        freq_z=(pl.col("tick_freq") - freq_mean) / freq_std
    )
    
    # 3. Whale Signature: Momentum Consistency (Directional Sweeps)
    # Sign of price change: 1 for up, -1 for down, 0 for no change
    df = df.with_columns(
        px_change=pl.col("mid").diff().fill_null(0).sign()
    )
    
    # Identify runs of same-direction ticks
    # We create a group id that changes whenever the direction changes
    df = df.with_columns(
        dir_change=(pl.col("px_change") != pl.col("px_change").shift(1)).fill_null(True)
    ).with_columns(
        group_id=pl.col("dir_change").cum_sum()
    )
    
    # Calculate duration and count of each same-direction run
    run_stats = df.group_by("group_id").agg([
        pl.len().alias("run_len"),
        pl.col("time_delta").sum().alias("run_duration"),
        pl.col("px_change").first().alias("direction"),
        pl.col("timestamp").first().alias("start_time"),
        pl.col("timestamp").last().alias("end_time"),
        pl.col("mid").first().alias("start_price"),
        pl.col("mid").last().alias("end_price")
    ])
    
    # Join back to highlight whale activity
    whales = run_stats.filter(
        (pl.col("run_len") >= tick_threshold) & 
        (pl.col("run_duration") <= time_ms_threshold) &
        (pl.col("direction") != 0)
    )
    
    # 4. Liquidity Absorption (Spread Spikes)
    # High frequency + widening spread during price move
    df = df.with_columns(
        spread_z=(pl.col("spread") - pl.col("spread").mean()) / pl.col("spread").std()
    )
    
    absorption_events = df.filter(
        (pl.col("freq_z") > z_threshold) & 
        (pl.col("spread_z") > 2)
    )
    
    return df, whales, absorption_events

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Whale Detection Model for Index Tick Data")
    parser.add_argument("--input", type=str, required=True, help="Path to tick parquet file")
    parser.add_argument("--tick_threshold", type=int, default=3)
    parser.add_argument("--time_threshold", type=int, default=500)
    parser.add_argument("--z_threshold", type=float, default=2.5)
    args = parser.parse_args()
    
    df, whales, absorption = detect_whales(args.input, args.tick_threshold, args.time_threshold, args.z_threshold)
    
    print("\n--- Whale Momentum Signatures (Rapid Directional Sweeps) ---")
    if len(whales) > 0:
        print(whales.sort("run_len", descending=True).head(10))
    else:
        print("No directional sweep whales detected.")
        
    print("\n--- Liquidity Absorption Events (Volatility/Spread Spikes) ---")
    if len(absorption) > 0:
        print(absorption.select(["timestamp", "mid", "spread", "tick_freq", "freq_z"]).head(10))
    else:
        print("No absorption events detected.")
        
    print(f"\nAnalysis complete. Total Ticks: {len(df)}, Whale Signature Clusters: {len(whales)}")
