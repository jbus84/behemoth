import polars as pl
import numpy as np
import os
import lightgbm as lgb
import warnings
warnings.filterwarnings("ignore")

def run_micro_audit():
    print(">>> MICRO-STRUCTURE AUDIT (1-MINUTE RAW) <<<")
    
    # Load Nasdaq Data (2023 + 2024)
    # Using 2023 as Train, 2024 as Test
    repo = "/Users/danielfisher/repositories/behemoth"
    files = [
        os.path.join(repo, "graph_dataset_1m_2023.parquet"),
        os.path.join(repo, "graph_dataset_1m_2024.parquet")
    ]
    
    dfs = []
    for f in files:
        if os.path.exists(f):
            d = pl.read_parquet(f)
            # Ensure price col is consistent
            if "NSXUSD" not in d.columns:
                if "NSXUSD_mid" in d.columns: d = d.with_columns(pl.col("NSXUSD_mid").alias("NSXUSD"))
                elif "close" in d.columns: d = d.with_columns(pl.col("close").alias("NSXUSD"))
            d = d.select(["timestamp", "NSXUSD"])
            dfs.append(d)
            
    if not dfs:
        print("No data found.")
        return
        
    df = pl.concat(dfs).sort("timestamp")
    
    # Features (1m)
    print("Calculating 1m Features...")
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
        pl.col("timestamp").dt.year().alias("year")
    ]).drop_nulls()
    
    # Target (Path Dependent +20/-10) on 1m bars
    close = df["NSXUSD"].to_numpy()
    
    horizon = 30 # 30 minutes
    tp = 20.0
    sl = 10.0
    
    long_labels = np.zeros(len(df), dtype=np.int32)
    long_outcomes = np.zeros(len(df))
    
    print("Labeling Targets...")
    for i in range(len(df) - horizon):
        entry = close[i]
        path = close[i+1 : i+horizon+1]
        changes = (path / entry - 1) * 10000
        
        ltp = np.where(changes > tp)[0]
        lsl = np.where(changes < -sl)[0]
        
        ft = ltp[0] if len(ltp)>0 else 9999
        fs = lsl[0] if len(lsl)>0 else 9999
        
        if ft < fs:
            long_labels[i] = 1
            long_outcomes[i] = tp
        elif fs < ft:
            long_labels[i] = 0
            long_outcomes[i] = -sl
        else:
            long_labels[i] = 0
            long_outcomes[i] = changes[-1]
            
    df = df.with_columns([
        pl.Series("long_labels", long_labels),
        pl.Series("long_outcomes", long_outcomes)
    ])
    
    # Split
    train_full = df.filter(pl.col("year") == 2023)
    test_full = df.filter(pl.col("year") == 2024)
    
    # --- REGIME FILTER (Vol > D7) ---
    print("\ncalculating Volatility Deciles on 2023 Class...")
    vol_train = train_full["vol_30m"].to_numpy() # Use 30m vol for regime? Or 5m?
    # User said "appropriate volatility regime". 
    # In 15m audit we used vol_1h. Here we have vol_30m and vol_5m.
    # vol_30m is more stable for "Regime". vol_5m is "Burst".
    # Let's use vol_30m to define the background regime.
    
    deciles = np.percentile(vol_train, np.linspace(0, 100, 11))
    d7_anchored = deciles[6]
    print(f"D7 Threshold (Anchored): {d7_anchored:.4f}")
    
    train = train_full.filter(pl.col("vol_30m") > d7_anchored)
    test = test_full.filter(pl.col("vol_30m") > d7_anchored)
    
    print(f"Training Samples (High Vol): {len(train)} / {len(train_full)}")
    print(f"Test Samples (High Vol): {len(test)} / {len(test_full)}")
    
    # Features
    feats = ["rsi_14", "roc_5m", "roc_15m", "vol_5m", "vol_30m"]
    X_train = train.select(feats).to_numpy()
    y_train = train["long_labels"].to_numpy()
    
    # Train
    print("Training LightGBM...")
    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    
    # Predict
    X_test = test.select(feats).to_numpy()
    probs = model.predict_proba(X_test)[:, 1]
    
    # Eval
    outcomes = test["long_outcomes"].to_numpy()
    
    print("\nRESULTS (Threshold Audit):")
    print(f"{'Threshold':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL':<10}")
    print("-" * 50)
    
    for thresh in [0.55, 0.60, 0.65, 0.70]:
        mask = probs > thresh
        n = np.sum(mask)
        if n > 0:
            pnl = outcomes[mask]
            net = np.mean(pnl) - 1.5
            wr = np.mean(pnl > 0)
            print(f"{thresh:<10} | {n:<8} | {wr:<10.1%} | {net:<10.2f} bps")
        else:
            print(f"{thresh:<10} | 0        | N/A        | N/A")

if __name__ == "__main__":
    run_micro_audit()
