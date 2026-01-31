import polars as pl
import os
import glob
from datetime import timedelta

# Config
TICK_DIR = "/Users/danielfisher/Desktop/tick/NSXUSD"
OUTPUT_DIR = "/Users/danielfisher/repositories/behemoth/data/swing"

def build_swing_data():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    # Get all tick files
    files = sorted(glob.glob(os.path.join(TICK_DIR, "*_ticks.parquet")))
    print(f"Found {len(files)} tick files.")
    
    # Process in chunks (Yearly?) to avoid RAM explosion, 
    # but we want a single continuous dataframe for 4H/Daily to ensure alignment?
    # Actually, we can process monthly, resample to 1m first (to reduce size), 
    # then concat and resample to 4H/1D.
    # Processing raw ticks to 4H directly is fine too, but 1m is a good intermediate.
    
    ohlc_1m_list = []
    
    for f in files:
        print(f"Processing {os.path.basename(f)}...")
        df = pl.read_parquet(f)
        
        # Ensure Timestamp is datetime
        # Tick schema: timestamp, bid, ask.
        # We use Mid Price for OHLC? Or Bid? Standard is Bid for charts usually, or Mid.
        # Let's use Bid to be consistent with "Selling" to exit? 
        # Actually, standard OHLC is usually Bid. Let's stick to Bid.
        
        # Resample to 1m first
        # We use explicit `set_sorted` to ensure dynamic_resample works
        df = df.sort("timestamp").with_columns([
            (pl.col("bid") + pl.col("ask")) / 2 # Mid
        ])
        
        # 1-Minute Aggregation
        q_1m = df.group_by_dynamic("timestamp", every="1m").agg([
            pl.col("bid").first().alias("open"),
            pl.col("bid").max().alias("high"),
            pl.col("bid").min().alias("low"),
            pl.col("bid").last().alias("close"),
            pl.count("bid").alias("tick_count")
        ])
        
        ohlc_1m_list.append(q_1m)

    print("Concatenating 1m Data...")
    full_1m = pl.concat(ohlc_1m_list).sort("timestamp")
    
    # Save 1m intermediate?
    # full_1m.write_parquet(os.path.join(OUTPUT_DIR, "NSXUSD_1m.parquet"))
    
    print("Resampling to 4H...")
    # 4H Blocks. 00:00, 04:00, 08:00...
    df_4h = full_1m.group_by_dynamic("timestamp", every="4h").agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("tick_count").sum().alias("volume")
    ])
    
    print(f"4H Rows: {len(df_4h)}")
    df_4h.write_parquet(os.path.join(OUTPUT_DIR, "NSXUSD_4h.parquet"))
    
    print("Resampling to 1H...")
    # 1H Blocks
    df_1h = full_1m.group_by_dynamic("timestamp", every="1h").agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("tick_count").sum().alias("volume")
    ])
    df_1h.write_parquet(os.path.join(OUTPUT_DIR, "NSXUSD_1h.parquet"))
    
    print("Resampling to Daily (D)...")
    # Daily Blocks. 00:00 UTC start.
    df_1d = full_1m.group_by_dynamic("timestamp", every="1d").agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("tick_count").sum().alias("volume")
    ])
    
    print(f"Daily Rows: {len(df_1d)}")
    df_1d.write_parquet(os.path.join(OUTPUT_DIR, "NSXUSD_1d.parquet"))
    
    print("Done!")

if __name__ == "__main__":
    build_swing_data()
