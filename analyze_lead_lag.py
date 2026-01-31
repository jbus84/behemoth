import polars as pl
import os
from pathlib import Path
import argparse
import numpy as np

def analyze_lead_lag(nsx_path, spx_path, sample_rate_ms=500, max_lags=20):
    print(f"Loading NSX: {nsx_path}")
    nsx = pl.read_parquet(nsx_path).select(["timestamp", "mid"]).rename({"mid": "nsx_px"})
    
    print(f"Loading SPX: {spx_path}")
    spx = pl.read_parquet(spx_path).select(["timestamp", "mid"]).rename({"mid": "spx_px"})
    
    # Resample to a fixed grid
    print(f"Resampling to {sample_rate_ms}ms grid...")
    
    start = max(nsx["timestamp"].min(), spx["timestamp"].min())
    end = min(nsx["timestamp"].max(), spx["timestamp"].max())
    
    grid = pl.datetime_range(start, end, f"{sample_rate_ms}ms", eager=True).to_frame("timestamp").with_columns(
        pl.col("timestamp").dt.cast_time_unit("ns")
    )
    
    # Join both to the grid
    combined = grid.join_asof(nsx, on="timestamp", strategy="backward")
    combined = combined.join_asof(spx, on="timestamp", strategy="backward")
    
    # Drop NAs and calculate returns
    combined = combined.drop_nulls().with_columns([
        ((pl.col("nsx_px") / pl.col("nsx_px").shift(1)) - 1).alias("nsx_ret"),
        ((pl.col("spx_px") / pl.col("spx_px").shift(1)) - 1).alias("spx_ret")
    ]).drop_nulls()
    
    print(f"Calculating Cross-Correlation for {max_lags} lags...")
    results = []
    
    nsx_ret = combined["nsx_ret"]
    spx_ret = combined["spx_ret"]
    
    for lag in range(-max_lags, max_lags + 1):
        # Correlate NSX with shifted SPX
        # lag > 0: SPX is shifted down (past values align with NSX current). -> SPX leads NSX.
        # lag < 0: SPX is shifted up (future values align with NSX current). -> NSX leads SPX.
        
        c_series = combined.select(
            pl.corr("nsx_ret", pl.col("spx_ret").shift(lag))
        ).to_series()
        
        c = c_series[0]
        results.append({
            "Lag_ms": lag * sample_rate_ms,
            "Correlation": float(c) if c is not None else 0.0
        })
        
    res_df = pl.DataFrame(results, schema={"Lag_ms": pl.Int64, "Correlation": pl.Float64})
    print("\n--- Cross-Correlation Results ---")
    print(res_df.sort("Correlation", descending=True).head(10))
    
    peak = res_df.sort(pl.col("Correlation").abs(), descending=True).head(1).to_dicts()[0]
    lag_val = peak["Lag_ms"]
    
    # Interpretation:
    # If peak is at lag L:
    # corr(NSX_t, SPX_{t-L}) is highest.
    # If L > 0: SPX_{t-L} correlates with NSX_t. -> SPX leads NSX.
    # If L < 0: SPX_{t+|L|} correlates with NSX_t. -> NSX leads SPX.
    
    # Wait, let's re-verify the shift logic.
    # x = [1, 2, 3]
    # y = [1, 2, 3]
    # y.shift(1) = [null, 1, 2]
    # corr(x, y.shift(1)) correlates:
    # x[1] (2) with y[0] (1)
    # x[2] (3) with y[1] (2)
    # This means y is the "past" version of x. -> y LEADS x.
    # So if Lag_ms > 0: SPX leads NSX.
    # If Lag_ms < 0: NSX leads SPX.
    
    if lag_val > 0:
        print(f"\nConclusion: S&P 500 appears to LEAD Nasdaq by ~{lag_val}ms (Correlation peak at lag {lag_val}ms).")
    elif lag_val < 0:
        print(f"\nConclusion: Nasdaq appears to LEAD S&P 500 by ~{abs(lag_val)}ms (Correlation peak at lag {lag_val}ms).")
    else:
        print("\nConclusion: The indices are perfectly co-integrated with no detectable lead-lag at this resolution.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nsx", type=str, required=True)
    parser.add_argument("--spx", type=str, required=True)
    parser.add_argument("--ms", type=int, default=100)
    args = parser.parse_args()
    
    analyze_lead_lag(args.nsx, args.spx, sample_rate_ms=args.ms)
