import polars as pl
import os
from pathlib import Path
import glob
import argparse

def analyze_fx_correlation(idx_path, fx_path, sample_rate_s=60):
    idx = pl.read_parquet(idx_path).select(["timestamp", "mid"]).rename({"mid": "idx_px"}).sort("timestamp")
    fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
    
    # Grid for alignment
    start = max(idx["timestamp"].min(), fx["timestamp"].min())
    end = min(idx["timestamp"].max(), fx["timestamp"].max())
    grid = pl.datetime_range(start, end, f"{sample_rate_s}s", eager=True).to_frame("timestamp").with_columns(
        pl.col("timestamp").dt.cast_time_unit("ns")
    )
    
    combined = grid.join_asof(idx, on="timestamp", strategy="backward")
    combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
    
    # Calculate returns
    combined = combined.with_columns([
        ((pl.col("idx_px") / pl.col("idx_px").shift(1)) - 1).alias("idx_ret"),
        ((pl.col("fx_px") / pl.col("fx_px").shift(1)) - 1).alias("fx_ret")
    ]).drop_nulls()
    
    if len(combined) < 2:
        return None
        
    corr = combined.select(pl.corr("idx_ret", "fx_ret")).to_series()[0]
    return corr

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=str, default="2025")
    args = parser.parse_args()

    root = Path("/Users/danielfisher/Desktop/tick")
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    indices = {
        "Nasdaq (NSXUSD)": "NSXUSD",
        "S&P 500 (SPXUSD)": "SPXUSD",
        "DAX (GRXEUR)": "GRXEUR",
        "FTSE 100 (UKXGBP)": "UKXGBP"
    }
    
    months = [f"{i:02d}" for i in range(1, 13)]
    
    all_results = []
    
    for month in months:
        ym = f"{args.year}{month}"
        month_res = {"YearMonth": ym}
        print(f"Analyzing {ym}...")
        
        for idx_label, idx_folder in indices.items():
            idx_file = root / idx_folder / f"{idx_folder}_{ym}_ticks.parquet"
            if not idx_file.exists():
                continue
                
            for fx in fx_pairs:
                fx_file = root / fx / f"{fx}_{ym}_ticks.parquet"
                if not fx_file.exists():
                    continue
                
                corr = analyze_fx_correlation(idx_file, fx_file)
                month_res[f"{idx_folder}_{fx}"] = round(corr, 4) if corr is not None else None
        
        if len(month_res) > 1:
            all_results.append(month_res)
            
    df = pl.DataFrame(all_results)
    print(f"\n--- Cross-Asset Correlation Analysis ({args.year}) ---")
    print(df)
    
    # Calculate averages per pair
    avg_res = {}
    for col in df.columns:
        if col == "YearMonth": continue
        avg_res[col] = round(df[col].mean(), 4)
    
    print("\n--- Average Correlations Across 2025 ---")
    for pair, avg in avg_res.items():
        print(f"{pair}: {avg}")

if __name__ == "__main__":
    main()
