import polars as pl
import os
import glob

def build_dax_data():
    print(">>> BUILDING DAX (GRXEUR) 1-MINUTE DATA <<<")
    
    source_dir = "/Users/danielfisher/Desktop/tick/GRXEUR"
    output_dir = "/Users/danielfisher/repositories/behemoth"
    years = [2023, 2024, 2025]
    
    if not os.path.exists(source_dir):
        print(f"Error: Source directory {source_dir} not found.")
        return

    for year in years:
        print(f"Processing Year: {year}...")
        
        pattern = os.path.join(source_dir, f"GRXEUR_{year}*_ticks.parquet")
        files = glob.glob(pattern)
        
        if not files:
            print(f"No files found for {year}. Skipping.")
            continue
            
        dfs = []
        for f in sorted(files):
            print(f"  Loading {os.path.basename(f)}...")
            try:
                lf = pl.scan_parquet(f)
                cols = pl.read_parquet(f, n_rows=1).columns
                
                price_expr = None
                if "price" in cols:
                    price_expr = pl.col("price")
                elif "bid_price" in cols and "ask_price" in cols:
                    price_expr = ((pl.col("bid_price") + pl.col("ask_price")) / 2)
                elif "bid" in cols:
                    price_expr = pl.col("bid")
                else:
                    price_expr = pl.col(cols[1])
                
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
            out_path = os.path.join(output_dir, f"dax_dataset_1m_{year}.parquet")
            
            # Alias close to GRXEUR for audit script compatibility
            full_year = full_year.with_columns(pl.col("close").alias("GRXEUR"))
            
            full_year.write_parquet(out_path)
            print(f"Saved {out_path} ({len(full_year)} 1m bars)")

if __name__ == "__main__":
    build_dax_data()
