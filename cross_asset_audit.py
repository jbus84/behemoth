import polars as pl
import numpy as np
import os
import seaborn as sns
import lightgbm as lgb
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_cross_asset():
    print(">>> CROSS-ASSET AUDIT (DAX LEAD-LAG) <<<")
    
    # Load 2023 NSX and GRX
    repo = "/Users/danielfisher/repositories/behemoth"
    f_nsx = os.path.join(repo, "graph_dataset_1m_2023.parquet")
    f_dax = os.path.join(repo, "dax_dataset_1m_2023.parquet")
    
    if not os.path.exists(f_nsx) or not os.path.exists(f_dax):
        print("Data missing.")
        return
        
    d_nsx = pl.read_parquet(f_nsx)
    d_dax = pl.read_parquet(f_dax)
    
    # Normalize col names
    if "NSXUSD_mid" in d_nsx.columns: d_nsx = d_nsx.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
    elif "close" in d_nsx.columns: d_nsx = d_nsx.with_columns(pl.col("close").alias("NSXUSD"))
    
    if "GRXEUR_mid" in d_dax.columns: d_dax = d_dax.with_columns(pl.col("GRXEUR_mid").alias("GRXEUR"))
    elif "close" in d_dax.columns: d_dax = d_dax.with_columns(pl.col("close").alias("GRXEUR"))
    
    # Join on Timestamp
    d_nsx = d_nsx.select(["timestamp", "NSXUSD"])
    d_dax = d_dax.select(["timestamp", "GRXEUR"])
    
    df = d_nsx.join(d_dax, on="timestamp", how="inner").sort("timestamp")
    print(f"Aligned Data Points: {len(df)}")
    
    # Features: DAX Moves (Lagged)
    # Important: We use PAST DAX moves to predict FUTURE NSX moves.
    # DAX ROC_5m means "Return over last 5m". Known at Time T.
    
    df = df.with_columns([
        (pl.col("GRXEUR") / pl.col("GRXEUR").shift(5) - 1).alias("dax_roc_5m"),
        (pl.col("GRXEUR") / pl.col("GRXEUR").shift(15) - 1).alias("dax_roc_15m"),
        (pl.col("GRXEUR") / pl.col("GRXEUR").shift(30) - 1).alias("dax_roc_30m"),
        
        # Target: NSX Future 30m Return
        ((pl.col("NSXUSD").shift(-30) / pl.col("NSXUSD") - 1) * 10000).alias("nsx_future_30m")
    ]).drop_nulls()
    
    # Check IC
    print("\n--- INFORMATION COEFFICIENT (DAX predicts NSX?) ---")
    
    sample = df.sample(n=100000, seed=42) # Bootstrap
    
    feats = ["dax_roc_5m", "dax_roc_15m", "dax_roc_30m"]
    y = sample["nsx_future_30m"].to_numpy()
    
    for f in feats:
        x = sample[f].to_numpy()
        corr, _ = spearmanr(x, y)
        print(f"{f:<15}: {corr:.4f}")
        
    print("\nIf correlations are > 0.02, we have a lead-lag edge.")
    print("If correlations are ~0.00, markets are efficient/simultaneous.")

if __name__ == "__main__":
    run_cross_asset()
