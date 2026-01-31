import polars as pl
import os
import glob

def build_spx_data():
    print(">>> BUILDING SPX 1-MINUTE DATA <<<")
    
    source_dir = "/Users/danielfisher/Desktop/tick/SPXUSD"
    output_dir = "/Users/danielfisher/repositories/behemoth"
    years = [2023, 2024, 2025]
    
    # Check if source exists
    if not os.path.exists(source_dir):
        print(f"Error: Source directory {source_dir} not found.")
        return

    for year in years:
        print(f"Processing Year: {year}...")
        
        # Find all monthly files for this year
        pattern = os.path.join(source_dir, f"SPXUSD_{year}*_ticks.parquet")
        files = glob.glob(pattern)
        
        if not files:
            print(f"No files found for {year}. Skipping.")
            continue
            
        dfs = []
        for f in sorted(files):
            print(f"  Loading {os.path.basename(f)}...")
            try:
                # Assuming standard tick schema: timestamp, bid_price/ask_price or price
                # Let's inspect schema on first file if needed, but standard is usually known.
                # We'll assume 'timestamp' and 'bid_price'/'ask_price' exist.
                # We'll use (bid+ask)/2 as price, or just bid. 
                # Let's try to read and check.
                
                # LAZY READ IS SAFER for schema
                lf = pl.scan_parquet(f)
                
                # Check columns (cheat by reading 1 row)
                cols = pl.read_parquet(f, n_rows=1).columns
                
                price_expr = None
                if "price" in cols:
                    price_expr = pl.col("price")
                elif "bid_price" in cols and "ask_price" in cols:
                    price_expr = ((pl.col("bid_price") + pl.col("ask_price")) / 2)
                elif "bid" in cols: # simplistic
                    price_expr = pl.col("bid")
                else:
                    # Fallback to whatever numeric is there? 
                    # Usually it's bid_price, ask_price.
                    price_expr = pl.col(cols[1]) # Risky?
                
                # Aggregate to 1m
                # We need to ensure 'timestamp' is sorted.
                q = (
                    lf
                    .with_columns(price_expr.alias("price"))
                    .sort("timestamp")
                    .group_by_dynamic("timestamp", every="1m")
                    .agg([
                        pl.col("price").first().alias("open"),
                        pl.col("price").max().alias("high"),
                        pl.col("price").min().alias("low"),
                        pl.col("price").last().alias("close")
                    ])
                )
                
                dfs.append(q.collect())
            except Exception as e:
                print(f"Error processing {f}: {e}")
                
        if dfs:
            full_year = pl.concat(dfs).sort("timestamp")
            
            # Save
            out_path = os.path.join(output_dir, f"spx_dataset_1m_{year}.parquet")
            
            # We must verify column naming for the audit script (Expected: SPXUSD)
            # The audit script looks for a target column. 
            # We should perform the rename to 'SPXUSD' (close price) OR keep OHLC.
            # My audit scripts usually use 'close' and rename it or use specific col.
            # spx_audit.py expected 'target' = 'SPXUSD'. 
            # But the 15m resampler uses 'target' to create 'close'.
            # So I should make sure the column 'SPXUSD' exists and contains the close price?
            # Or just save standard OHLC and update audit script to use 'close'.
            # Standard OHLC is cleaner ("open", "high", "low", "close").
            # I will save as "open", "high", "low", "close", "SPXUSD" (copy of close).
            
            full_year = full_year.with_columns(pl.col("close").alias("SPXUSD"))
            
            full_year.write_parquet(out_path)
            print(f"Saved {out_path} ({len(full_year)} 1m bars)")

if __name__ == "__main__":
    build_spx_data()
