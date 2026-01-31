import polars as pl
import numpy as np
import os
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_fx_audit():
    print(">>> FX VOLATILITY LEAD-LAG AUDIT <<<")
    
    repo = "/Users/danielfisher/repositories/behemoth"
    
    # Load Nasdaq
    f_nsx = os.path.join(repo, "graph_dataset_1m_2023.parquet") # Just 2023 for now or both?
    f_nsx_24 = os.path.join(repo, "graph_dataset_1m_2024.parquet")
    
    # Load FX
    fx_files = {
        "EURUSD": ["eurusd_dataset_1m_2023.parquet", "eurusd_dataset_1m_2024.parquet"],
        "GBPUSD": ["gbpusd_dataset_1m_2023.parquet", "gbpusd_dataset_1m_2024.parquet"],
        "USDJPY": ["usdjpy_dataset_1m_2023.parquet", "usdjpy_dataset_1m_2024.parquet"]
    }
    
    # Load NSX
    dfs_nsx = []
    if os.path.exists(f_nsx): dfs_nsx.append(pl.read_parquet(f_nsx))
    if os.path.exists(f_nsx_24): dfs_nsx.append(pl.read_parquet(f_nsx_24))
    
    if not dfs_nsx:
        print("NSX Data missing")
        return
        
    df_nsx = pl.concat(dfs_nsx)
    if "NSXUSD_mid" in df_nsx.columns: df_nsx = df_nsx.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
    elif "close" in df_nsx.columns: df_nsx = df_nsx.with_columns(pl.col("close").alias("NSXUSD"))
    
    df_nsx = df_nsx.select(["timestamp", "NSXUSD"]).sort("timestamp")
    
    # Calculate NSX Volatility (Regime Definition)
    df_nsx = df_nsx.with_columns(
        ((pl.col("NSXUSD") / pl.col("NSXUSD").shift(1) - 1) * 10000).alias("ret_1m")
    )
    df_nsx = df_nsx.with_columns(
        pl.col("ret_1m").rolling_std(30).alias("vol_30m"),
        ((pl.col("NSXUSD").shift(-30) / pl.col("NSXUSD") - 1) * 10000).alias("future_ret_30m")
    ).drop_nulls()
    
    # Determine Vol Thresholds (D8)
    vol_vals = df_nsx["vol_30m"].to_numpy()
    d8 = np.percentile(vol_vals, 80)
    print(f"Nasdaq Volatility D8 Threshold: {d8:.4f}")
    
    # Load FX and Join
    for pair, files in fx_files.items():
        print(f"\n--- {pair} Analysis ---")
        dfs_fx = []
        for f in files:
            p = os.path.join(repo, f)
            if os.path.exists(p): dfs_fx.append(pl.read_parquet(p))
            
        if not dfs_fx:
            print(f"No data for {pair}")
            continue
            
        df_fx = pl.concat(dfs_fx).sort("timestamp")
        
        # Ensure col name
        col_name = pair
        if pair not in df_fx.columns:
            # Maybe lower case in file?
            if pair.lower() in df_fx.columns: df_fx = df_fx.rename({pair.lower(): pair})
            elif "close" in df_fx.columns: df_fx = df_fx.rename({"close": pair})
        
        # Calculate FX Returns (Features)
        # Lagged: Return over LAST 5m, 15m
        df_fx = df_fx.with_columns([
            (pl.col(pair) / pl.col(pair).shift(5) - 1).alias(f"{pair}_roc_5m"),
            (pl.col(pair) / pl.col(pair).shift(15) - 1).alias(f"{pair}_roc_15m")
        ])
        
        # Join
        joined = df_nsx.join(df_fx, on="timestamp", how="inner")
        
        # Regime Filter
        high_vol = joined.filter(pl.col("vol_30m") > d8)
        low_vol = joined.filter(pl.col("vol_30m") <= d8)
        
        print(f"Sample Size (All): {len(joined)}")
        print(f"Sample Size (High Vol > {d8:.2f}): {len(high_vol)}")
        
        # Correlations
        feats = [f"{pair}_roc_5m", f"{pair}_roc_15m"]
        target = "future_ret_30m"
        
        print("Correlations (ALL REGIMES):")
        for ft in feats:
            c, _ = spearmanr(joined[ft].to_numpy(), joined[target].to_numpy())
            print(f"  {ft:<15}: {c:.4f}")
            
        print("Correlations (HIGH VOL REGIME):")
        for ft in feats:
            c, _ = spearmanr(high_vol[ft].to_numpy(), high_vol[target].to_numpy())
            print(f"  {ft:<15}: {c:.4f}")
            
        # Check Directionality
        # If USDJPY crashes (Negative ROC), does NSX crash (Negative Future)?
        # Positive Correlation expected? Or Negative?
        # USDJPY down = Yen Strength = Risk Off = Nasdaq Down. So Positive Correlation.
        
        if abs(c) > 0.02:
            print(f"--> POTENTIAL SIGNAL found in {pair} (High Vol)!")

if __name__ == "__main__":
    run_fx_audit()
