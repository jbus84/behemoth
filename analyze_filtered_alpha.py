import polars as pl
import os
from pathlib import Path
import argparse
import datetime
import numpy as np
from whale_detector import detect_whales

def analyze_filtered_alpha(parquet_path, tick_threshold=4, time_threshold=500, z_threshold=2.5, spread_z_min=1.5, forward_windows_sec=[10, 30, 60]):
    # Detect all whale events
    df, whales, absorption = detect_whales(parquet_path, tick_threshold, time_threshold, z_threshold)
    
    if len(whales) == 0:
        print("No whale signals to analyze.")
        return
    
    # Sort for join_asof
    df = df.sort("timestamp")
    
    # Calculate Spread Z-Score in the main df
    df = df.with_columns(
        spread_z=(pl.col("spread") - pl.col("spread").mean()) / pl.col("spread").std()
    )
    
    # Map the spread_z at the time of the event back to the whales list
    whale_events = whales.select([
        "end_time", 
        "direction", 
        "end_price", 
        "group_id"
    ]).sort("end_time")
    
    whale_events = whale_events.join_asof(
        df.select(["timestamp", "spread", "spread_z"]),
        left_on="end_time",
        right_on="timestamp",
        strategy="backward"
    )
    
    # Apply the High-Conviction Filter: Only trade when the sweep happens during a spread spike
    filtered_whales = whale_events.filter(pl.col("spread_z") >= spread_z_min)
    
    print(f"\n--- Filtering Analysis: Spread Z-Score >= {spread_z_min} ---")
    print(f"Total Whale Sweeps: {len(whale_events)}")
    print(f"High-Conviction Sweeps: {len(filtered_whales)} ({round(len(filtered_whales)/len(whale_events)*100, 1)}%)")
    
    if len(filtered_whales) == 0:
        print("No filtered events found.")
        return

    results = []
    
    for window in forward_windows_sec:
        # Time to target
        targets = filtered_whales.with_columns(
            target_time=(pl.col("end_time") + datetime.timedelta(seconds=window)).dt.cast_time_unit("ns")
        )
        
        # Get exit price (Mid)
        analysis = targets.join_asof(
            df.select(["timestamp", "mid"]),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        # Calculate Gross Return (bps) - Fading the sweep
        analysis = analysis.with_columns(
            gross_bps=((pl.col("end_price") - pl.col("mid")) / pl.col("end_price")) * 10000 * pl.col("direction")
        )
        
        # Calculate Spread Cost (bps)
        analysis = analysis.with_columns(
            spread_bps=(pl.col("spread") / pl.col("end_price")) * 10000
        )
        
        # Net Return
        analysis = analysis.with_columns(
            net_bps=pl.col("gross_bps") - pl.col("spread_bps")
        )
        
        avg_gross = analysis["gross_bps"].mean()
        avg_spread = analysis["spread_bps"].mean()
        avg_net = analysis["net_bps"].mean()
        win_rate_net = (analysis["net_bps"] > 0).mean()
        
        results.append({
            "Window (sec)": window,
            "Gross (bps)": round(avg_gross, 2),
            "Spread (bps)": round(avg_spread, 2),
            "Net (bps)": round(avg_net, 2),
            "Net Win %": round(win_rate_net * 100, 1)
        })
    
    print(pl.DataFrame(results).sort("Window (sec)"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--tick_threshold", type=int, default=4)
    parser.add_argument("--time_threshold", type=int, default=500)
    parser.add_argument("--z_threshold", type=float, default=2.5)
    parser.add_argument("--spread_z", type=float, default=2.0) # Conservative threshold
    args = parser.parse_args()
    
    analyze_filtered_alpha(args.input, args.tick_threshold, args.time_threshold, args.z_threshold, args.spread_z)
