import polars as pl
import os
from pathlib import Path
import argparse
import datetime
from whale_detector import detect_whales

def analyze_alpha(parquet_path, tick_threshold=4, time_threshold=500, z_threshold=2.5, forward_windows_sec=[10, 30, 60, 300]):
    # Detect events
    df, whales, absorption = detect_whales(parquet_path, tick_threshold, time_threshold, z_threshold)
    
    if len(whales) == 0:
        print("No whale signals to analyze.")
        return
    
    # We want to see the price movement after each 'end_time' of a whale run
    # Join with the original df to get the price at t + window
    df = df.sort("timestamp")
    
    whale_events = whales.select(["end_time", "direction", "end_price"]).sort("end_time")
    
    results = []
    
    for window in forward_windows_sec:
        # For each event, find the price at timestamp + window
        # We use join_asof for efficient nearest-neighbor lookup
        targets = whale_events.with_columns(
            target_time=(pl.col("end_time") + datetime.timedelta(seconds=window)).dt.cast_time_unit("ns")
        )
        
        # Join with df to get the price at target_time
        analysis = targets.join_asof(
            df.select(["timestamp", "mid"]),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward" # Look at the NEXT available tick
        )
        
        # Calculate return in bps
        # (Price_after / Price_now - 1) * 10000 * direction
        analysis = analysis.with_columns(
            ret_bps=((pl.col("mid") / pl.col("end_price")) - 1) * 10000 * pl.col("direction")
        )
        
        avg_ret = analysis["ret_bps"].mean()
        win_rate = (analysis["ret_bps"] > 0).mean()
        
        results.append({
            "Window (sec)": window,
            "Avg Return (bps)": round(avg_ret, 2),
            "Win Rate": round(win_rate * 100, 1)
        })
    
    print(f"\n--- Whale Signal Alpha Analysis ({Path(parquet_path).name}) ---")
    print(pl.DataFrame(results))
    print("\nInterpretation: 'Avg Return' > 0 means the price continued in the whale's direction.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--tick_threshold", type=int, default=4)
    parser.add_argument("--time_threshold", type=int, default=500)
    parser.add_argument("--z_threshold", type=float, default=2.5)
    args = parser.parse_args()
    
    analyze_alpha(args.input, args.tick_threshold, args.time_threshold, args.z_threshold)
