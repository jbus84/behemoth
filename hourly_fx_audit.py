import polars as pl
import numpy as np
import os
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_hourly_fx_audit():
    print(">>> HOURLY FX VOLATILITY AUDIT <<<")
    
    repo = "/Users/danielfisher/repositories/behemoth"
    
    # Load 1m Data (to be resampled)
    # We load 2023 and 2024 to get a good sample size for Hourly
    years = ["2023", "2024"]
    
    def load_pair(pair_name, file_prefix):
        dfs = []
        for y in years:
            f = os.path.join(repo, f"{file_prefix}_dataset_1m_{y}.parquet")
            if os.path.exists(f):
                try:
                    d = pl.read_parquet(f)
                    # Helper to standardize column name to `pair_name`
                    # 1. Identify valid columns
                    cols = d.columns
                    target_col = None
                    
                    # Preference list
                    candidates = [pair_name, pair_name.lower(), f"{pair_name}_mid", "close", "price"]
                    
                    for c in candidates:
                        if c in cols:
                            target_col = c
                            break
                    
                    if target_col:
                        # Select only timestamp and the target column, aliasing it to pair_name
                        d = d.select([
                            pl.col("timestamp"),
                            pl.col(target_col).alias(pair_name)
                        ])
                        dfs.append(d)
                except Exception as e:
                    print(f"Error loading {f}: {e}")
                    
        if dfs:
            return pl.concat(dfs).sort("timestamp")
        return None

    print("Loading Data...")
    nsx = load_pair("NSXUSD", "graph") # graph_dataset_1m_...
    if nsx is None: nsx = load_pair("NSXUSD", "nsx") # Fallback
    
    eur = load_pair("EURUSD", "eurusd")
    gbp = load_pair("GBPUSD", "gbpusd")
    jpy = load_pair("USDJPY", "usdjpy")
    
    if nsx is None:
        print("CRITICAL: NSX Data Not Found")
        return

    # Resample to Hourly
    def to_hourly(df, col):
        return df.group_by_dynamic("timestamp", every="1h", closed="right", label="right").agg([
            pl.col(col).last().alias(col)
        ]).sort("timestamp")

    print("Resampling to Hourly...")
    nsx_1h = to_hourly(nsx, "NSXUSD")
    
    # Calculate Regime (Hourly Volatility)
    nsx_1h = nsx_1h.with_columns(
        ((pl.col("NSXUSD") / pl.col("NSXUSD").shift(1) - 1) * 10000).alias("ret_1h")
    ).with_columns(
        pl.col("ret_1h").rolling_std(24).alias("vol_24h"), # Daily Vol context
        ((pl.col("NSXUSD").shift(-1) / pl.col("NSXUSD") - 1) * 10000).alias("target_next_1h")
    ).drop_nulls()

    # Determine Vol Threshold (D8)
    vol_vals = nsx_1h["vol_24h"].to_numpy()
    d8 = np.percentile(vol_vals, 80)
    print(f"Hourly Volatility D8 Threshold: {d8:.4f} bps")

    # Process FX
    fx_map = {"EURUSD": eur, "GBPUSD": gbp, "USDJPY": jpy}
    
    for name, df in fx_map.items():
        if df is None: continue
        print(f"\n--- {name} (Hourly) ---")
        
        df_1h = to_hourly(df, name)
        
        # Calculate FX Features (Current Hour Return)
        # We want to use FX return at time T to predict NSX return at time T+1?
        # Or FX return at time T-1?
        # "FX Leads Indices".
        # If FX moves at 10:00-11:00, does NSX move at 11:00-12:00?
        # Yes, that is Lag 1.
        
        df_1h = df_1h.with_columns(
            (pl.col(name) / pl.col(name).shift(1) - 1).alias(f"{name}_ret_1h")
        )
        
        # Join
        joined = nsx_1h.join(df_1h, on="timestamp", how="inner")
        
        # Filter Regime
        high_vol = joined.filter(pl.col("vol_24h") > d8)
        
        print(f"Samples (High Vol): {len(high_vol)}")
        
        # Correlation
        feat = f"{name}_ret_1h"
        target = "target_next_1h"
        
        c_all, _ = spearmanr(joined[feat].to_numpy(), joined[target].to_numpy())
        c_high, _ = spearmanr(high_vol[feat].to_numpy(), high_vol[target].to_numpy())
        
        print(f"Correlation (All):      {c_all:.4f}")
        print(f"Correlation (High Vol): {c_high:.4f}")
        
        if abs(c_high) > 0.05:
            print(f"--> SIGNIFICANT SIGNAL in {name}!")

if __name__ == "__main__":
    run_hourly_fx_audit()
