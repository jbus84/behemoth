import polars as pl
import os
from pathlib import Path
import argparse
import datetime

def analyze_burst_lead(idx_path, fx_path, burst_threshold_bps=2.0, forward_windows=[5, 10, 30, 60]):
    print(f"Analyzing {Path(fx_path).name} bursts vs {Path(idx_path).name}...")
    
    # Load and resample to 1s
    idx = pl.read_parquet(idx_path).select(["timestamp", "mid"]).rename({"mid": "idx_px"}).sort("timestamp")
    fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
    
    start = max(idx["timestamp"].min(), fx["timestamp"].min())
    end = min(idx["timestamp"].max(), fx["timestamp"].max())
    grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").with_columns(
        pl.col("timestamp").dt.cast_time_unit("ns")
    )
    
    combined = grid.join_asof(idx, on="timestamp", strategy="backward")
    combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
    
    # 1. Identify FX Bursts
    # Burst = return over last 5 seconds > threshold
    combined = combined.with_columns(
        fx_ret_5s=((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000
    )
    
    bursts = combined.filter(pl.col("fx_ret_5s").abs() > burst_threshold_bps)
    
    if len(bursts) == 0:
        return None

    print(f"Detected {len(bursts)} FX bursts. Calculating follow-through...")
    
    results = []
    for window in forward_windows:
        # For each burst at T, look at Index at T + window
        targets = bursts.select(["timestamp", "idx_px", "fx_ret_5s"]).with_columns(
            target_time=pl.col("timestamp") + datetime.timedelta(seconds=window)
        ).with_columns(pl.col("target_time").dt.cast_time_unit("ns"))
        
        analysis = targets.join_asof(
            combined.select(["timestamp", "idx_px"]).rename({"idx_px": "idx_px_after"}),
            left_on="target_time",
            right_on="timestamp",
            strategy="forward"
        )
        
        # Weighted Directional Win: Does index move in direction of FX burst?
        analysis = analysis.with_columns(
            idx_move_bps=((pl.col("idx_px_after") / pl.col("idx_px")) - 1) * 10000 * pl.col("fx_ret_5s").sign()
        )
        
        avg_move = analysis["idx_move_bps"].mean()
        win_rate = (analysis["idx_move_bps"] > 0).mean()
        
        results.append({
            "Window (s)": window,
            "Avg Move (bps)": round(avg_move, 3),
            "Win Rate %": round(win_rate * 100, 1)
        })
        
    return pl.DataFrame(results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsx", type=str, required=True)
    parser.add_argument("--spx", type=str, required=True)
    parser.add_argument("--fx_root", type=str, required=True)
    parser.add_argument("--ym", type=str, default="202512")
    args = parser.parse_args()

    root = Path(args.fx_root)
    indices = {"Nasdaq": args.nsx, "S&P 500": args.spx}
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    
    output = []
    for idx_name, idx_path in indices.items():
        for fx in fx_pairs:
            fx_path = root / fx / f"{fx}_{args.ym}_ticks.parquet"
            if not fx_path.exists(): continue
            
            res = analyze_burst_lead(idx_path, fx_path)
            if res is not None:
                # Get the best window (highest win rate or move)
                res = res.with_columns(Index=pl.lit(idx_name), FX=pl.lit(fx))
                output.append(res)
                
    if output:
        final_df = pl.concat(output)
        print("\n--- FX Burst as Leading Indicator (2bps Trigger) ---")
        print(final_df.sort(["Index", "Win Rate %"], descending=[True, True]))
    else:
        print("No significant bursts detected in this timeframe.")

if __name__ == "__main__":
    main()
