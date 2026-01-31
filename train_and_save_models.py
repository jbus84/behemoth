import polars as pl
import numpy as np
import os
import lightgbm as lgb
import json
import shutil

def train_and_save():
    print(">>> BUILDING PRODUCTION MODELS (ANCHOR: 2023) <<<")
    
    # Setup Paths
    repo_path = "/Users/danielfisher/repositories/behemoth"
    model_dir = os.path.join(repo_path, "models")
    if os.path.exists(model_dir):
        shutil.rmtree(model_dir)
    os.makedirs(model_dir)
    
    assets = [
        {"name": "NSXUSD", "file": "graph_dataset_1m_2023.parquet"},
        {"name": "SPXUSD", "file": "spx_dataset_1m_2023.parquet"},
        {"name": "GRXEUR", "file": "dax_dataset_1m_2023.parquet"}
    ]
    
    master_config = {}
    
    for asset in assets:
        print(f"\nProcessing {asset['name']}...")
        
        # Load 2023 Data
        p = os.path.join(repo_path, asset['file'])
        if not os.path.exists(p):
            print(f"Error: 2023 data not found for {asset['name']}")
            continue
            
        df = pl.read_parquet(p).sort("timestamp")
        target_col = asset['name']
        if target_col not in df.columns:
             # Fallback logic from audits
             if "NSXUSD_mid" in df.columns: target_col = "NSXUSD_mid"
             # SPX/DAX builder aliased col to asset name, so should be fine.
        
        # 15m Resample
        df_15m = df.group_by_dynamic("timestamp", every="15m").agg([
            pl.col(target_col).last().alias("close")
        ]).sort("timestamp")
        
        # Feature Engineering (Production Standard)
        def calc_rsi(expr, n=14):
            delta = expr.diff()
            u = delta.clip(lower_bound=0)
            d = delta.clip(upper_bound=0).abs()
            rs = u.rolling_mean(n) / (d.rolling_mean(n) + 1e-9)
            return 100 - (100 / (1 + rs))

        df_15m = df_15m.with_columns(
            ((pl.col("close").log() - pl.col("close").shift(1).log()) * 10000).alias("ret_15m")
        ).drop_nulls()
        
        df_15m = df_15m.with_columns([
            calc_rsi(pl.col("close"), 14).alias("rsi_14"),
            (pl.col("close") / pl.col("close").shift(4) - 1).alias("roc_1h"),
            (pl.col("close") / pl.col("close").shift(16) - 1).alias("roc_4h"),
            pl.col("ret_15m").rolling_std(4).alias("vol_1h"),
            pl.col("ret_15m").rolling_std(16).alias("vol_4h")
        ]).drop_nulls()
        
        df_15m = df_15m.with_columns(
            (pl.col("vol_1h") / (pl.col("vol_4h") + 1e-9)).alias("vol_ratio")
        ).drop_nulls()
        
        # Volatility Thresholds (Anchored 2023)
        vol_vals = df_15m["vol_1h"].to_numpy()
        deciles = np.percentile(vol_vals, np.linspace(0, 100, 11))
        d7 = deciles[6]
        d10 = deciles[9]
        
        # Targets (+20/-10)
        # Note: We need 1m data for path labeling
        ts_1m = df["timestamp"].to_numpy()
        close_1m = df[target_col].to_numpy()
        ts_15m = df_15m["timestamp"].to_numpy()
        
        long_labels = np.zeros(len(df_15m), dtype=np.int32)
        short_labels = np.zeros(len(df_15m), dtype=np.int32)
        
        start_indices = np.searchsorted(ts_1m, ts_15m)
        horizon_m = 60
        tp = 20.0
        sl = 10.0
        
        for i, start_idx in enumerate(start_indices):
            if start_idx + horizon_m >= len(close_1m): continue
            entry = close_1m[start_idx]
            path = close_1m[start_idx+1 : start_idx + horizon_m + 1]
            changes = (path / entry - 1) * 10000
            
            # Long
            ltp = np.where(changes > tp)[0]
            lsl = np.where(changes < -sl)[0]
            flt = ltp[0] if len(ltp)>0 else 9999
            fls = lsl[0] if len(lsl)>0 else 9999
            if flt < fls: long_labels[i] = 1
            
            # Short
            stp = np.where(changes < -tp)[0]
            ssl = np.where(changes > sl)[0]
            fst = stp[0] if len(stp)>0 else 9999
            fss = ssl[0] if len(ssl)>0 else 9999
            if fst < fss: short_labels[i] = 1
            
        # Train Models
        features = ["rsi_14", "roc_1h", "roc_4h", "vol_ratio", "vol_1h"]
        X = df_15m.select(features).to_numpy()
        
        # Long Model
        model_long = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
        model_long.fit(X, long_labels)
        path_l = os.path.join(model_dir, f"{asset['name']}_long.txt")
        model_long.booster_.save_model(path_l)
        print(f"  Saved Long Model: {path_l}")
        
        # Short Model
        model_short = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
        model_short.fit(X, short_labels)
        path_s = os.path.join(model_dir, f"{asset['name']}_short.txt")
        model_short.booster_.save_model(path_s)
        print(f"  Saved Short Model: {path_s}")
        
        # Update Master Config
        master_config[asset['name']] = {
            "vol_d7": d7,
            "vol_d10": d10,
            "models": {
                "long": f"{asset['name']}_long.txt",
                "short": f"{asset['name']}_short.txt"
            }
        }
        
    # Save Config
    with open(os.path.join(model_dir, "config.json"), "w") as f:
        json.dump(master_config, f, indent=4)
    print("\nSaved models/config.json")

if __name__ == "__main__":
    train_and_save()
