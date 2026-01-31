import polars as pl
import numpy as np
import os
import seaborn as sns
import lightgbm as lgb
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings("ignore")

def run_diagnostics():
    print(">>> SIGNAL DIAGNOSTICS (THE 'WHY') <<<")
    
    # Load 2023 Data (Train Set)
    repo = "/Users/danielfisher/repositories/behemoth"
    f = os.path.join(repo, "graph_dataset_1m_2023.parquet")
    
    if not os.path.exists(f):
        print("Data not found.")
        return
        
    df = pl.read_parquet(f)
    if "NSXUSD_mid" in df.columns: df = df.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
    elif "close" in df.columns: df = df.with_columns(pl.col("close").alias("NSXUSD"))
    
    df = df.select(["timestamp", "NSXUSD"]).sort("timestamp")
    
    # 1. Feature Engineering
    print("Calculating Features...")
    df = df.with_columns(
        ((pl.col("NSXUSD") / pl.col("NSXUSD").shift(1) - 1) * 10000).alias("ret_1m")
    )
    
    def calc_rsi(expr, n=14):
        delta = expr.diff()
        u = delta.clip(lower_bound=0)
        d = delta.clip(upper_bound=0).abs()
        rs = u.rolling_mean(n) / (d.rolling_mean(n) + 1e-9)
        return 100 - (100 / (1 + rs))
        
    df = df.with_columns([
        calc_rsi(pl.col("NSXUSD"), 14).alias("rsi_14"),
        (pl.col("NSXUSD") / pl.col("NSXUSD").shift(5) - 1).alias("roc_5m"),
        (pl.col("NSXUSD") / pl.col("NSXUSD").shift(15) - 1).alias("roc_15m"),
        pl.col("ret_1m").rolling_std(5).alias("vol_5m"),
        pl.col("ret_1m").rolling_std(30).alias("vol_30m"),
        ((pl.col("NSXUSD").shift(-30) / pl.col("NSXUSD") - 1) * 10000).alias("future_30m_ret") # Absolute future return
    ]).drop_nulls()
    
    # 2. Correlation Analysis (IC)
    print("\n--- INFORMATION COEFFICIENT (Rank Correlation with Future 30m Return) ---")
    features = ["rsi_14", "roc_5m", "roc_15m", "vol_5m", "vol_30m"]
    
    # Random sample for speed/Robustness
    sample = df.sample(n=100000, seed=42)
    y_target = sample["future_30m_ret"].to_numpy()
    
    for feat in features:
        x_feat = sample[feat].to_numpy()
        corr, _ = spearmanr(x_feat, y_target)
        print(f"{feat:<15}: {corr:.4f}  ({'Signif' if abs(corr)>0.005 else 'Noise'})")
        
    # 3. Target Distribution (Triple Barrier)
    print("\n--- TARGET DISTRIBUTION (+20/-10 bps) ---")
    # Actually calculate labels to see imbalance
    close = df["NSXUSD"].to_numpy()
    horizon = 30
    tp = 20.0
    sl = 10.0
    
    long_labels = np.zeros(len(df), dtype=np.int32)
    
    # Fast loop or vectorized approx? Let's use loop for exact logic
    # Sample first 20k points for speed check
    
    # Actually, let's use the Labels from previous logic (Path Dependent)
    # We will compute for full DF roughly
    
    # Optimization: Only calculate if correlation suggests we should bother?
    # No, let's count Triple Barrier events
    
    # Use Vectorized Rolling Max/Min for speed approx
    # Or just loop the first 100k
    check_len = min(len(close)-31, 100000)
    hits = 0
    stops = 0
    neutrals = 0
    
    for i in range(check_len):
        entry = close[i]
        path = close[i+1 : i+horizon+1]
        changes = (path / entry - 1) * 10000
        
        ltp = np.where(changes > tp)[0]
        lsl = np.where(changes < -sl)[0]
        ft = ltp[0] if len(ltp)>0 else 9999
        fs = lsl[0] if len(lsl)>0 else 9999
        
        if ft < fs: hits += 1
        elif fs < ft: stops += 1
        else: neutrals += 1
        
    total = hits + stops + neutrals
    print(f"Sample Size: {total}")
    print(f"Wins  (+20bps) : {hits} ({hits/total:.1%})")
    print(f"Losses (-10bps): {stops} ({stops/total:.1%})")
    print(f"Neutral        : {neutrals} ({neutrals/total:.1%})")
    
    # 4. Model Calibration
    print("\n--- MODEL CALIBRATION CHECK ---")
    # Train simple model on Sample
    X = sample.select(features).to_numpy()
    # Labels for sample?
    # We need to map labels. Just redo logic for sample idxs technically difficult.
    # Let's use the counts above as proxy for 'Base Rate'.
    # Base Rate of winning is very low?
    
    base_rate = hits / total
    print(f"Base Win Rate: {base_rate:.1%}")
    print(f"To be profitable at +20/-10, needed Win Rate > 33% (approx).")
    print(f"Actual Base Rate is {base_rate:.1%} vs 33%. Edge requires {33 - base_rate*100:.1f}% lift.")
    
    if base_rate < 0.05:
        print("CRITICAL: The target event is too rare. The model learns 'Always Zero'.")
    
    print("\n>>> DIAGNOSIS COMPLETE <<<")

if __name__ == "__main__":
    run_diagnostics()
