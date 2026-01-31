import polars as pl
import os
import glob

def build_fx_data():
    print(">>> BUILDING FX 1-MINUTE DATA <<<")
    
    source_root = "/Users/danielfisher/Desktop/tick"
    output_dir = "/Users/danielfisher/repositories/behemoth"
    years = [2023, 2024]
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF"]
    
    for pair in pairs:
        print(f"\nProcessing {pair}...")
        pair_dir = os.path.join(source_root, pair)
        
        if not os.path.exists(pair_dir):
            print(f"  Error: Directory {pair_dir} not found.")
            continue

        for year in years:
            print(f"  Year: {year}...")
            
            # Pattern: PAIR_YYYYMM_ticks.parquet
            pattern = os.path.join(pair_dir, f"{pair}_{year}*_ticks.parquet")
            files = glob.glob(pattern)
            
            if not files:
                print(f"    No files found for {year}.")
                continue
                
            dfs = []
            for f in sorted(files):
                try:
                    # Scan to be safe, or read
                    # FX Tick data usually: timestamp, bid_price, ask_price OR price
                    # Helper to canonicalize
                    cols = pl.read_parquet(f, n_rows=1).columns
                    
                    price_expr = None
                    if "price" in cols: price_expr = pl.col("price")
                    elif "bid_price" in cols and "ask_price" in cols:
                        price_expr = (pl.col("bid_price") + pl.col("ask_price")) / 2
                    elif "bid" in cols: price_expr = pl.col("bid")
                    else: price_expr = pl.col(cols[1]) # Fallback
                    
                    q = (
                        pl.scan_parquet(f)
                        .with_columns(price_expr.alias("price"))
                        .sort("timestamp")
                        .group_by_dynamic("timestamp", every="1m", closed="right", label="right")
                        .agg([
                            pl.col("price").last().alias("close")
                        ])
                    )
                    dfs.append(q.collect())
                except Exception as e:
                    print(f"    Error reading {f}: {e}")
                    
            if dfs:
                full_year = pl.concat(dfs).sort("timestamp")
                # Rename close to Pair Name
                full_year = full_year.with_columns(pl.col("close").alias(pair))
                
                out_path = os.path.join(output_dir, f"{pair.lower()}_dataset_1m_{year}.parquet")
                full_year.write_parquet(out_path)
                print(f"    Saved {out_path}")

if __name__ == "__main__":
    build_fx_data()
