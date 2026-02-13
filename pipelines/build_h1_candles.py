"""
Builds 1-Hour OHLC candles from M15 Parquet Data.
Input: data/global_15m/{SYMBOL}_15m.parquet
Output: data/global_1h/{SYMBOL}_1h.parquet
"""
import os
import glob
import polars as pl
from pathlib import Path

INPUT_DIR = "data/global_15m"
OUTPUT_DIR = "data/global_1h"

def build_h1_candles():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    parquet_files = glob.glob(os.path.join(INPUT_DIR, "*_15m.parquet"))
    print(f"Found {len(parquet_files)} M15 files in {INPUT_DIR}")
    
    for fpath in parquet_files:
        filename = os.path.basename(fpath)
        # format: SYM_15m.parquet
        symbol = filename.split("_")[0]
        
        print(f"Processing {symbol}...")
        try:
            df = pl.read_parquet(fpath)
            
            # Find close column
            close_col = f"close_{symbol}"
            if close_col not in df.columns:
                print(f"  Warning: Column {close_col} not found in {filename}. Columns: {df.columns}")
                # Fallback: find any column starting with close_ ?
                candidates = [c for c in df.columns if c.startswith("close_")]
                if candidates:
                    close_col = candidates[0]
                    print(f"  Using {close_col} instead.")
                else:
                    print(f"  Skipping {symbol} (no close col)")
                    continue
            
            # Resample M15 -> H1
            # We take the *last* close of the hour as the H1 close.
            candles = (
                df.sort("timestamp")
                .group_by_dynamic("timestamp", every="1h")
                .agg([
                    pl.col(close_col).first().alias("open"),
                    pl.col(close_col).max().alias("high"),
                    pl.col(close_col).min().alias("low"),
                    pl.col(close_col).last().alias("close")
                ])
            )
            
            out_path = os.path.join(OUTPUT_DIR, f"{symbol}_1h.parquet")
            candles.write_parquet(out_path)
            print(f"  Saved {len(candles)} candles to {out_path}")
            
        except Exception as e:
            print(f"  Error processing {symbol}: {e}")

if __name__ == "__main__":
    build_h1_candles()
