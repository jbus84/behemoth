import polars as pl
import os
from pathlib import Path
import argparse
import datetime as dt
import numpy as np

def calculate_ccf(idx_df, fx_df, max_lag_ms=5000, sample_rate_ms=1000):
    # returns should already be calculated or we calculate them here
    # We join and align
    start = max(idx_df["timestamp"].min(), fx_df["timestamp"].min())
    end = min(idx_df["timestamp"].max(), fx_df["timestamp"].max())
    grid = pl.datetime_range(start, end, f"{sample_rate_ms}ms", eager=True).to_frame("timestamp").with_columns(
        pl.col("timestamp").dt.cast_time_unit("ns")
    )
    
    combined = grid.join_asof(idx_df, on="timestamp", strategy="backward")
    combined = combined.join_asof(fx_df, on="timestamp", strategy="backward").drop_nulls()
    
    max_lag_steps = int(max_lag_ms / sample_rate_ms)
    if len(combined) < max_lag_steps * 2:
        return None
        
    combined = combined.with_columns([
        ((pl.col("idx_px") / pl.col("idx_px").shift(1)) - 1).alias("idx_ret"),
        ((pl.col("fx_px") / pl.col("fx_px").shift(1)) - 1).alias("fx_ret")
    ]).drop_nulls()
    
    idx_ret = combined["idx_ret"].to_numpy()
    fx_ret = combined["fx_ret"].to_numpy()
    
    lags = range(-max_lag_steps, max_lag_steps + 1)
    results = []
    
    for lag in lags:
        if lag < 0:
            # FX leads Index (Index shifted forward)
            c = np.corrcoef(fx_ret[:lag], idx_ret[-lag:])[0, 1]
        elif lag > 0:
            # Index leads FX (FX shifted forward)
            c = np.corrcoef(fx_ret[lag:], idx_ret[:-lag])[0, 1]
        else:
            c = np.corrcoef(fx_ret, idx_ret)[0, 1]
        
        results.append({"lag_ms": lag * sample_rate_ms, "correlation": c})
        
    return pl.DataFrame(results)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsx", type=str, required=True)
    parser.add_argument("--spx", type=str, required=True)
    parser.add_argument("--fx_root", type=str, required=True)
    parser.add_argument("--ym", type=str, default="202512")
    parser.add_argument("--sample-ms", type=int, default=1000)
    parser.add_argument("--max-lag-ms", type=int, default=5000)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    args = parser.parse_args()

    root = Path(args.fx_root)
    indices = {
        "Nasdaq": args.nsx,
        "S&P 500": args.spx
    }
    
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    
    all_leads = []
    
    for idx_name, idx_path in indices.items():
        print(f"\nAnalyzing Lead-Lag for {idx_name}...")
        idx_df = pl.read_parquet(idx_path).select(["timestamp", "mid"]).rename({"mid": "idx_px"}).sort("timestamp")

        if args.start and args.end:
            start_dt = dt.datetime.fromisoformat(args.start)
            end_dt = dt.datetime.fromisoformat(args.end)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=dt.timezone.utc)
            idx_df = idx_df.filter(
                (pl.col("timestamp") >= pl.lit(start_dt))
                & (pl.col("timestamp") <= pl.lit(end_dt))
            )
        
        for fx in fx_pairs:
            fx_path = root / fx / f"{fx}_{args.ym}_ticks.parquet"
            if not fx_path.exists():
                continue
                
            fx_df = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
            if args.start and args.end:
                fx_df = fx_df.filter(
                    (pl.col("timestamp") >= pl.lit(start_dt))
                    & (pl.col("timestamp") <= pl.lit(end_dt))
                )
            
            ccf = calculate_ccf(
                idx_df, fx_df, max_lag_ms=args.max_lag_ms, sample_rate_ms=args.sample_ms
            )
            if ccf is not None:
                # Find max correlation and at which lag it occurs
                # We care about NEGATIVE lags (FX leads)
                best = ccf.filter(pl.col("lag_ms") <= 0).sort("correlation", descending=True).head(1)
                
                if not best.is_empty():
                    all_leads.append({
                        "Index": idx_name,
                        "FX Pair": fx,
                        "Peak Lag (ms)": abs(best["lag_ms"][0]),
                        "Peak Corr": round(best["correlation"][0], 4)
                    })

    print("\n--- FX Leading Indicator Analysis (Peak Cross-Correlation) ---")
    print(pl.DataFrame(all_leads).sort("Peak Corr", descending=True))
    print("\nNote: Peak Lag is the number of milliseconds FX moves BEFORE the Index.")

if __name__ == "__main__":
    main()
