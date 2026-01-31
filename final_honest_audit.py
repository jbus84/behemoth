import polars as pl
import numpy as np
import os
import lightgbm as lgb
import glob

def run_honest_audit():
    print(">>> FINAL HONEST AUDIT (Anchored Deciles / No Look-Ahead) <<<")
    
    # 1. Load Data
    search_path = "/Users/danielfisher/repositories/behemoth"
    
    # Configuration
    assets = [
        {"name": "NSXUSD", "file_pattern": "graph_dataset_1m_{year}.parquet", "spread": 1.5, "prob_thresh": 0.65},
        {"name": "SPXUSD", "file_pattern": "spx_dataset_1m_{year}.parquet", "spread": 1.5, "prob_thresh": 0.65},
        {"name": "GRXEUR", "file_pattern": "dax_dataset_1m_{year}.parquet", "spread": 1.5, "prob_thresh": 0.65}
    ]
    
    for asset in assets:
        print(f"\n=== AUDITING {asset['name']} ===")
        
        dfs = []
        years = ["2023", "2024", "2025"]
        for y in years:
            fname = asset['file_pattern'].format(year=y)
            p = os.path.join(search_path, fname)
            if os.path.exists(p):
                d = pl.read_parquet(p)
                d = d.with_columns(pl.lit(int(y)).alias("year"))
                dfs.append(d)
        
        if not dfs:
            print(f"No data for {asset['name']}")
            continue
            
        df_1m = pl.concat(dfs).sort("timestamp")
        target_col = asset['name']
        if target_col not in df_1m.columns:
            # Fallback for NSX if needed (usually NSXUSD or NSXUSD_mid)
            if "NSXUSD_mid" in df_1m.columns: target_col = "NSXUSD_mid"
            else: 
                # SPX might be 'close' if builder logic was simple
                # My builder mapped close -> SPXUSD.
                pass
        
        # 15m Resample (Right-Labeled to avoid Leakage)
        df_15m = df_1m.group_by_dynamic("timestamp", every="15m", closed="right", label="right").agg([
            pl.col(target_col).last().alias("close"),
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

        # Targets (+20/-10)
        ts_1m = df_1m["timestamp"].to_numpy()
        close_1m = df_1m[target_col].to_numpy()
        ts_15m = df_15m["timestamp"].to_numpy()
        
        long_outcomes = np.zeros(len(df_15m))
        short_outcomes = np.zeros(len(df_15m))
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
            hit_tp = np.where(changes > tp)[0]
            hit_sl = np.where(changes < -sl)[0]
            ft = hit_tp[0] if len(hit_tp)>0 else 9999
            fs = hit_sl[0] if len(hit_sl)>0 else 9999
            
            if ft < fs:
                long_labels[i] = 1
                long_outcomes[i] = tp
            elif fs < ft:
                long_labels[i] = 0
                long_outcomes[i] = -sl
            else:
                long_labels[i] = 0
                long_outcomes[i] = changes[-1]
                
            # Short
            hit_tp_s = np.where(changes < -tp)[0]
            hit_sl_s = np.where(changes > sl)[0]
            ft_s = hit_tp_s[0] if len(hit_tp_s)>0 else 9999
            fs_s = hit_sl_s[0] if len(hit_sl_s)>0 else 9999
            
            if ft_s < fs_s:
                short_labels[i] = 1
                short_outcomes[i] = tp
            elif fs_s < ft_s:
                short_labels[i] = 0
                short_outcomes[i] = -sl
            else:
                short_labels[i] = 0
                short_outcomes[i] = -changes[-1]
                
        df_15m = df_15m.with_columns([
            pl.Series("long_labels", long_labels),
            pl.Series("short_labels", short_labels)
        ])
        
        # Train / Test Split
        train = df_15m.filter(pl.col("year") == 2023)
        test = df_15m.filter(pl.col("year") > 2023)
        
        features = ["rsi_14", "roc_1h", "roc_4h", "vol_ratio", "vol_1h"]
        X_train = train.select(features).to_numpy()
        
        # --- ANCHORED DECILES (The Fix) ---
        # Calculate thresholds on TRAIN data (2023)
        vol_train = train["vol_1h"].to_numpy()
        deciles_train = np.percentile(vol_train, np.linspace(0, 100, 11))
        
        d7_anchored = deciles_train[6] # D7 lower bound
        d10_anchored = deciles_train[9] # D10 lower bound
        
        print(f"Dataset 2023 (Train) Volatility Profile:")
        print(f"  D7 Threshold: {d7_anchored:.2f} bps")
        print(f"  D10 Threshold: {d10_anchored:.2f} bps")
        print(f"  (These fixed values will be applied to 2024/2025)")
        
        # Models
        model_long = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
        model_long.fit(X_train, train["long_labels"].to_numpy())
        
        model_short = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
        model_short.fit(X_train, train["short_labels"].to_numpy())
        
        # Predict Test
        X_test = test.select(features).to_numpy()
        probs_long = model_long.predict_proba(X_test)[:, 1]
        probs_short = model_short.predict_proba(X_test)[:, 1]
        
        # Evaluation
        vol_test = test["vol_1h"].to_numpy()
        year_test = test["year"].to_numpy()
        
        # Re-extract outcomes (safe slice logic)
        # Note: concat(train, test) is not guaranteed if we loaded lists.
        # But here we did: `df_1m = pl.concat(dfs).sort("timestamp")`.
        # And we filtered train/test from the resampled df_15m.
        # So test indices are just the latter part.
        
        # Actually safer to map outcomes via `test` indices relative to `df_15m`?
        # df_15m is monotonic time. Train < 2024 <= Test.
        # So we can just slice outcomes by length.
        test_offset = len(train)
        l_out_test = long_outcomes[test_offset:]
        s_out_test = short_outcomes[test_offset:]
        
        print(f"\nResults (Anchored Vol > {d7_anchored:.2f}, < {d10_anchored:.2f} | Prob > {asset['prob_thresh']}):")
        print(f"{'Year':<6} | {'Side':<6} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL':<10}")
        print("-" * 60)
        
        spread = asset['spread']
        prob_thresh = asset['prob_thresh']
        
        for y_test in [2024, 2025]:
            # Apply Fixed Thresholds from 2023
            mask_base = (year_test == y_test) & \
                        (vol_test >= d7_anchored) & (vol_test < d10_anchored)
            
            # Long
            mask_l = mask_base & (probs_long > prob_thresh)
            n_l = np.sum(mask_l)
            if n_l > 0:
                p_l = l_out_test[mask_l]
                net_l = np.mean(p_l) - spread
                wr_l = np.mean(p_l > 0)
                print(f"{y_test:<6} | {'Long':<6} | {n_l:<8} | {wr_l:<10.1%} | {net_l:<10.2f} bps")
            else:
                print(f"{y_test:<6} | {'Long':<6} | 0        | N/A        | N/A")
                
            # Short
            mask_s = mask_base & (probs_short > prob_thresh)
            n_s = np.sum(mask_s)
            if n_s > 0:
                p_s = s_out_test[mask_s]
                net_s = np.mean(p_s) - spread
                wr_s = np.mean(p_s > 0)
                print(f"{y_test:<6} | {'Short':<6} | {n_s:<8} | {wr_s:<10.1%} | {net_s:<10.2f} bps")
            else:
                print(f"{y_test:<6} | {'Short':<6} | 0        | N/A        | N/A")

if __name__ == "__main__":
    run_honest_audit()
