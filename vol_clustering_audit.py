import polars as pl
import numpy as np
import os

def run_vol_clustering_audit():
    print(">>> VOLATILITY CLUSTERING AUDIT (Feature 60m Swings) <<<")
    
    dfs = []
    years = ["2023", "2024", "2025"]
    search_path = "/Users/danielfisher/repositories/behemoth"
    
    for y in years:
        p = os.path.join(search_path, f"graph_dataset_1m_{y}.parquet")
        if os.path.exists(p):
            d = pl.read_parquet(p)
            d = d.with_columns(pl.lit(int(y)).alias("year"))
            dfs.append(d)
            
    if not dfs: return
    df_1m = pl.concat(dfs).sort("timestamp")
    target = "NSXUSD" if "NSXUSD" in df_1m.columns else "NSXUSD_mid"
    
    # 15m Resample
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col(target).last().alias("close"),
        pl.col(target).max().alias("high"),
        pl.col(target).min().alias("low"),
        pl.col(target).first().alias("open")
    ]).sort("timestamp")
    
    # Current Volatility (15m Range)
    df_15m = df_15m.with_columns(
        (((pl.col("high") / pl.col("low") - 1) * 10000)).alias("curr_15m_range")
    ).drop_nulls()
    
    # Future 60m Swing (Next 4 bars)
    # We want Max(High, next 4) - Min(Low, next 4)
    # Use rolling window shifted back
    
    # Window size 4, calc max high and min low
    indexer = pl.col("high").shift(-4).rolling_max(4) # This gets max of t+1..t+4? 
    # Rolling is usually backward looking. 
    # Shift(-4) moves t+4 to t.
    # Rolling(4) on t+4 includes t+4, t+3, t+2, t+1. 
    # Yes.
    
    future_high = pl.col("high").shift(-4).rolling_max(4)
    future_low = pl.col("low").shift(-4).rolling_min(4)
    
    df_15m = df_15m.with_columns([
        future_high.alias("fut_60m_high"),
        future_low.alias("fut_60m_low")
    ])
    
    df_15m = df_15m.with_columns(
        (((pl.col("fut_60m_high") / pl.col("fut_60m_low") - 1) * 10000)).alias("fut_60m_swing")
    ).drop_nulls()

    # Deciles of Current 15m Range
    rng_numpy = df_15m["curr_15m_range"].to_numpy()
    deciles = np.percentile(rng_numpy, np.linspace(0, 100, 11))
    
    print(f"\n{'Curr 15m Range':<20} | {'Next 60m Swing':<15} | {'Multiplier':<10}")
    print("-" * 55)
    
    for i in range(10):
        lower = deciles[i]
        upper = deciles[i+1]
        
        subset = df_15m.filter((pl.col("curr_15m_range") >= lower) & (pl.col("curr_15m_range") < upper))
        
        curr_avg = subset["curr_15m_range"].mean()
        fut_swing = subset["fut_60m_swing"].mean()
        multiplier = fut_swing / (curr_avg + 1e-9)
        
        label = f"D{i+1} ({lower:.1f}-{upper:.1f} bps)"
        print(f"{label:<20} | {fut_swing:<15.2f} bps | {multiplier:<10.2f}x")

if __name__ == "__main__":
    run_vol_clustering_audit()
