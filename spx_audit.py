import polars as pl
import numpy as np
import os
import lightgbm as lgb
import glob

def run_spx_audit():
    print(">>> SPX AUDIT (Bilateral Sniper) <<<")
    
    dfs = []
    # Note: Filenames are spx_dataset_1m_YYYY.parquet
    search_path = "/Users/danielfisher/repositories/behemoth"
    
    for y in ["2023", "2024", "2025"]:
        p = os.path.join(search_path, f"spx_dataset_1m_{y}.parquet")
        if os.path.exists(p):
            d = pl.read_parquet(p)
            d = d.with_columns(pl.lit(int(y)).alias("year"))
            dfs.append(d)
        else:
            print(f"Warning: {p} not found.")
            
    if not dfs: return
    df_1m = pl.concat(dfs).sort("timestamp")
    
    # Target column is "SPXUSD" from builder
    target = "SPXUSD"
    if target not in df_1m.columns:
        print(f"Error: Column {target} not found. Available: {df_1m.columns}")
        return
    
    # 15m Resample
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col(target).last().alias("close"),
        pl.col("year").first().alias("year")
    ]).sort("timestamp")
    
    # Features
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
    
    # --- BILATERAL TARGETS ---
    ts_1m = df_1m["timestamp"].to_numpy()
    close_1m = df_1m[target].to_numpy()
    ts_15m = df_15m["timestamp"].to_numpy()
    
    long_labels = np.zeros(len(df_15m), dtype=np.int32)
    long_outcomes = np.zeros(len(df_15m))
    short_labels = np.zeros(len(df_15m), dtype=np.int32)
    short_outcomes = np.zeros(len(df_15m))
    
    start_indices = np.searchsorted(ts_1m, ts_15m)
    horizon_m = 60
    tp_bps = 20.0
    sl_bps = 10.0
    
    for i, start_idx in enumerate(start_indices):
        if start_idx + horizon_m >= len(close_1m): continue
        entry = close_1m[start_idx]
        path = close_1m[start_idx+1 : start_idx + horizon_m + 1]
        changes = (path / entry - 1) * 10000
        
        # Long Logic
        ltp = np.where(changes > tp_bps)[0]
        lsl = np.where(changes < -sl_bps)[0]
        fltp = ltp[0] if len(ltp) > 0 else 9999
        flsl = lsl[0] if len(lsl) > 0 else 9999
        
        if fltp < flsl:
            long_labels[i] = 1
            long_outcomes[i] = tp_bps
        elif flsl < fltp:
            long_labels[i] = 0
            long_outcomes[i] = -sl_bps
        else:
            long_labels[i] = 0
            long_outcomes[i] = changes[-1] # Time exit
            
        # Short Logic
        stp = np.where(changes < -tp_bps)[0]
        ssl = np.where(changes > sl_bps)[0]
        fstp = stp[0] if len(stp) > 0 else 9999
        fssl = ssl[0] if len(ssl) > 0 else 9999
        
        if fstp < fssl:
            short_labels[i] = 1
            short_outcomes[i] = tp_bps
        elif fssl < fstp:
            short_labels[i] = 0
            short_outcomes[i] = -sl_bps
        else:
            short_labels[i] = 0
            short_outcomes[i] = -changes[-1] # Short PnL = -(Exit-Entry) = -Change

    df_15m = df_15m.with_columns([
        pl.Series("long_target", long_labels),
        pl.Series("short_target", short_labels)
    ])
    
    train = df_15m.filter(pl.col("year") == 2023)
    test = df_15m.filter(pl.col("year") > 2023)
    
    features = ["rsi_14", "roc_1h", "roc_4h", "vol_ratio", "vol_1h"]
    X_train = train.select(features).to_numpy()
    y_train_long = train["long_target"].to_numpy()
    y_train_short = train["short_target"].to_numpy()
    
    model_long = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
    model_long.fit(X_train, y_train_long)
    
    model_short = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
    model_short.fit(X_train, y_train_short)
    
    X_test = test.select(features).to_numpy()
    probs_long = model_long.predict_proba(X_test)[:, 1]
    probs_short = model_short.predict_proba(X_test)[:, 1]
    
    # Audit filters
    vol_test = test["vol_1h"].to_numpy()
    deciles = np.percentile(vol_test, np.linspace(0, 100, 11))
    d7_low = deciles[6]
    d10_low = deciles[9]
    
    print(f"\nSPX Volatility Thresholds: D7={d7_low:.2f} bps, D10={d10_low:.2f} bps")
    
    years_test = test["year"].to_numpy()
    
    # Re-extract outcomes
    # Since we sliced test from df_15m, outcomes are also sliced.
    # Note: we need to map indices or assume contiguity. 
    # df_15m was sorted by timestamp. train/test are filter.
    # concat(train, test) == df_15m IF years are contiguous.
    # Let's align by year filter on outcomes arrays.
    
    is_test = (df_15m["year"] > 2023).to_numpy()
    l_out = long_outcomes[is_test]
    s_out = short_outcomes[is_test]
    
    print(f"\n[SPX SNIPER AUDIT] (Filters: D7-D9, Prob > 0.65)")
    print("-" * 65)
    print(f"{'Year':<6} | {'Side':<6} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL':<10}")
    
    for y in [2024, 2025]:
        mask_base = (years_test == y) & (vol_test >= d7_low) & (vol_test < d10_low)
        
        # Longs
        mask_long = mask_base & (probs_long > 0.65)
        nl = np.sum(mask_long)
        if nl > 0:
            pl_long = l_out[mask_long]
            net_l = np.mean(pl_long) - 1.5
            wr_l = np.mean(pl_long > 0)
            print(f"{y:<6} | {'Long':<6} | {nl:<8} | {wr_l:<10.1%} | {net_l:<10.2f} bps")
        else:
            print(f"{y:<6} | {'Long':<6} | 0        | N/A        | N/A")

        # Shorts
        mask_short = mask_base & (probs_short > 0.65)
        ns = np.sum(mask_short)
        if ns > 0:
            pl_short = s_out[mask_short]
            net_s = np.mean(pl_short) - 1.5
            wr_s = np.mean(pl_short > 0)
            print(f"{y:<6} | {'Short':<6} | {ns:<8} | {wr_s:<10.1%} | {net_s:<10.2f} bps")
        else:
            print(f"{y:<6} | {'Short':<6} | 0        | N/A        | N/A")

if __name__ == "__main__":
    run_spx_audit()
