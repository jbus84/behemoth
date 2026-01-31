import polars as pl
import numpy as np
import os

def run_volatility_profile():
    print(">>> VOLATILITY REGIME CHARACTERISTICS <<<")
    
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
        pl.col(target).first().alias("open"),
        pl.col("year").first().alias("year")
    ]).sort("timestamp")
    
    # Calculate Volatility (ATR-like or StdDev)
    df_15m = df_15m.with_columns(
        ((pl.col("close").log() - pl.col("close").shift(1).log()) * 10000).alias("ret_15m")
    ).drop_nulls()
    
    df_15m = df_15m.with_columns(
        pl.col("ret_15m").rolling_std(4).alias("vol_1h") # 1h Volatility
    ).drop_nulls()
    
    # Features to analyze
    # 1. Body Ratio (Trendiness): Abs(Close-Open) / (High-Low)
    # 2. Autocorrelation (Persistence): Correlation of Ret(t) with Ret(t-1)
    # 3. Spread Cost: 1.5bps / (High-Low bps)
    
    df_15m = df_15m.with_columns([
        ((pl.col("close")-pl.col("open")).abs() / (pl.col("high")-pl.col("low") + 1e-9)).alias("body_ratio"),
        (((pl.col("high") / pl.col("low") - 1) * 10000)).alias("range_bps")
    ])
    
    # Deciles of Volatility
    vol_numpy = df_15m["vol_1h"].to_numpy()
    deciles = np.percentile(vol_numpy, np.linspace(0, 100, 11))
    
    print(f"\n{'Vol Decile':<15} | {'Range(bps)':<10} | {'Spread Cost%':<12} | {'Body Ratio':<10} | {'Next Ret':<10}")
    print("-" * 75)
    
    for i in range(10):
        lower = deciles[i]
        upper = deciles[i+1]
        
        subset = df_15m.filter((pl.col("vol_1h") >= lower) & (pl.col("vol_1h") < upper))
        
        avg_range = subset["range_bps"].mean()
        spread_cost = (1.5 / avg_range) * 100 if avg_range > 0 else 100
        body_ratio = subset["body_ratio"].mean()
        
        # Next Return Absolute (Opportunity)
        next_move = subset["ret_15m"].abs().mean()
        
        label = f"D{i+1} ({lower:.1f}-{upper:.1f})"
        
        print(f"{label:<15} | {avg_range:<10.2f} | {spread_cost:<11.1f}% | {body_ratio:<10.3f} | {next_move:<10.2f}")

if __name__ == "__main__":
    run_volatility_profile()
