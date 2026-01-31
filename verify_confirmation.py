import polars as pl
import os
from pathlib import Path
import argparse
import datetime

def verify_confirmation_alpha(nsx_path, spx_path, breakout_window_bins=10, sample_rate_ms=1000):
    print(f"Loading data...")
    nsx = pl.read_parquet(nsx_path).select(["timestamp", "mid"]).rename({"mid": "nsx_px"})
    spx = pl.read_parquet(spx_path).select(["timestamp", "mid"]).rename({"mid": "spx_px"})
    
    # Align to 1s grid
    start = max(nsx["timestamp"].min(), spx["timestamp"].min())
    end = min(nsx["timestamp"].max(), spx["timestamp"].max())
    grid = pl.datetime_range(start, end, f"{sample_rate_ms}ms", eager=True).to_frame("timestamp").with_columns(
        pl.col("timestamp").dt.cast_time_unit("ns")
    )
    
    combined = grid.join_asof(nsx, on="timestamp", strategy="backward")
    combined = combined.join_asof(spx, on="timestamp", strategy="backward").drop_nulls()
    
    # 1. Define Nasdaq Breakout
    # A breakout is when the price moves > N standard deviations over the last M bins
    combined = combined.with_columns([
        pl.col("nsx_px").pct_change().alias("nsx_ret"),
        pl.col("spx_px").pct_change().alias("spx_ret")
    ])
    
    # Calculate rolling volatility for breakout detection
    combined = combined.with_columns(
        nsx_vol=pl.col("nsx_ret").rolling_std(window_size=30) # 30s vol
    )
    
    # Breakout Signal: Absolute return > 2 * Vol
    combined = combined.with_columns(
        nsx_breakout=(pl.col("nsx_ret").abs() > 2 * pl.col("nsx_vol")).fill_null(False)
    )
    
    breakouts = combined.filter(pl.col("nsx_breakout"))
    
    if len(breakouts) == 0:
        print("No Nasdaq breakouts detected.")
        return

    print(f"Detected {len(breakouts)} Nasdaq micro-breakouts. Analyzing SPX follow-through...")
    
    results = []
    # Test windows: 5s, 10s, 30s, 60s
    for window_sec in [5, 10, 30, 60]:
        # For each breakout at time T, get SPX price at T + window
        targets = breakouts.select(["timestamp", "nsx_ret", "spx_px"]).with_columns(
            target_time=pl.col("timestamp") + datetime.timedelta(seconds=window_sec)
        ).with_columns(
            pl.col("target_time").dt.cast_time_unit("ns")
        )
        
        analysis = targets.join_asof(
            combined.select(["timestamp", "spx_px"]).rename({"spx_px": "spx_px_after"}),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        # Calculate SPX follow-through (direction-matched)
        # return = (px_after / px_now - 1) * sign(nsx_ret)
        analysis = analysis.with_columns(
            follow_bps=((pl.col("spx_px_after") / pl.col("spx_px")) - 1) * 10000 * pl.col("nsx_ret").sign()
        )
        
        avg_bps = analysis["follow_bps"].mean()
        win_rate = (analysis["follow_bps"] > 0).mean()
        
        results.append({
            "Window (s)": window_sec,
            "Avg Follow (bps)": round(avg_bps, 2),
            "Win Rate %": round(win_rate * 100, 1)
        })
        
    print(f"\n--- Nasdaq Breakout Leading SPX Follow-through ---")
    print(pl.DataFrame(results))
    print("\nInterpretation: If Avg Follow > 0 and Win Rate > 50%, the Nasdaq lead aggregates into a usable SPX signal.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsx", type=str, required=True)
    parser.add_argument("--spx", type=str, required=True)
    args = parser.parse_args()
    
    verify_confirmation_alpha(args.nsx, args.spx)
