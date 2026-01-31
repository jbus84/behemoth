import polars as pl
import numpy as np
import os
import lightgbm as lgb

def run_path_validity_check():
    print(">>> PATH VALIDITY CHECK (Conservative Execution) <<<")
    
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
    
    # 15m Resample for Model Inputs
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col(target).last().alias("close"),
        pl.col("year").first().alias("year")
    ]).sort("timestamp")
    
    # Feature Eng (Same as before)
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
    
    # STRICT Target Logic
    ts_1m = df_1m["timestamp"].to_numpy()
    close_1m = df_1m["close"].to_numpy()
    high_1m = df_1m["high"].to_numpy() # Need High/Low for strict check
    low_1m = df_1m["low"].to_numpy()
    
    ts_15m = df_15m["timestamp"].to_numpy()
    
    target_barrier = np.zeros(len(df_15m), dtype=np.int32)
    trade_outcomes = np.zeros(len(df_15m))
    ambiguous_count = 0
    
    start_indices = np.searchsorted(ts_1m, ts_15m)
    horizon_m = 60
    tp_bps = 20.0
    sl_bps = 10.0
    
    for i, start_idx in enumerate(start_indices):
        if start_idx + horizon_m >= len(close_1m): continue
        entry = close_1m[start_idx]
        
        # Look at the PATH of Highs and Lows
        path_high = high_1m[start_idx+1 : start_idx + horizon_m + 1]
        path_low = low_1m[start_idx+1 : start_idx + horizon_m + 1]
        
        # Calculate changes relative to entry
        changes_high = (path_high / entry - 1) * 10000
        changes_low = (path_low / entry - 1) * 10000
        
        # Check barriers
        hit_tp = np.where(changes_high > tp_bps)[0]
        hit_sl = np.where(changes_low < -sl_bps)[0]
        
        first_tp = hit_tp[0] if len(hit_tp) > 0 else 9999
        first_sl = hit_sl[0] if len(hit_sl) > 0 else 9999
        
        outcome = 0.0
        label = 0
        
        if first_tp < first_sl:
            # TP hit first? 
            # Check for Ambiguity: Did SL ALSO happen in the SAME bar?
            idx_tp = first_tp
            if changes_low[idx_tp] < -sl_bps:
                # Ambiguous Bar! High > TP and Low < SL in same minute.
                # Conservative: Assume SL happened first.
                label = 0
                outcome = -sl_bps
                ambiguous_count += 1
            else:
                label = 1
                outcome = tp_bps
        elif first_sl < first_tp:
            # SL hit first.
            label = 0
            outcome = -sl_bps
        else:
            # Time exit.
            outcome = (close_1m[start_idx + horizon_m] / entry - 1) * 10000
            label = 0
            
        target_barrier[i] = label
        trade_outcomes[i] = outcome
            
    # Train Model
    df_15m = df_15m.with_columns(pl.Series("target_barrier", target_barrier))
    
    train = df_15m.filter(pl.col("year") == 2023)
    test = df_15m.filter(pl.col("year") > 2023)
    
    features = ["rsi_14", "roc_1h", "roc_4h", "vol_ratio", "vol_1h"]
    X_train = train.select(features).to_numpy()
    y_train = train["target_barrier"].to_numpy()
    
    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    
    X_test = test.select(features).to_numpy()
    probs = model.predict_proba(X_test)[:, 1]
    
    # Audit Results
    years_test = test["year"].to_numpy()
    outcomes_test = trade_outcomes[len(train):] # Approx slice? No, need logical map due to resets?
    # Better: Re-extract outcomes based on indices
    # Actually, the dataframe 'test' is contiguous after 'train' in our creation flow?
    # Yes, we concatenated years in order.
    # trade_outcomes is parallel to df_15m.
    # So we just slice it.
    
    start_test_idx = len(train)
    outcomes_sub = trade_outcomes[start_test_idx : start_test_idx + len(test)]
    vol_test = test["vol_1h"].to_numpy()
    
    # D7-D9 Cutoff (Recalculate or use approx from prev)
    # Filter: Decile 7-9. (Approx 8.5 to 19.2 bps). 
    # Let's use hardcoded approximations from previous robust audit to be consistent.
    # Actually, calculate deciles on test set for fairness.
    deciles = np.percentile(vol_test, np.linspace(0, 100, 11))
    d7_low = deciles[6]
    d10_low = deciles[9]
    
    print(f"\n[STRICT PATH AUDIT] (Ambiguous Bars treated as LOSS)")
    print(f"Ambiguous Events detected in History: {ambiguous_count}")
    print(f"Filter: {d7_low:.2f} <= Vol < {d10_low:.2f} | Prob > 0.65")
    print("-" * 55)
    
    for y in [2024, 2025]:
        mask = (years_test == y) & \
               (vol_test >= d7_low) & (vol_test < d10_low) & \
               (probs > 0.65)
        
        n_trades = np.sum(mask)
        if n_trades == 0:
            print(f"{y:<6} | 0        | N/A")
            continue
            
        pnl = outcomes_sub[mask]
        net_pnl = np.mean(pnl) - 1.5
        win_rate = np.mean(pnl > 0)
        
        print(f"{y:<6} | {n_trades:<8} | {win_rate:<10.1%} | {net_pnl:<10.2f} bps")

if __name__ == "__main__":
    run_path_validity_check()
