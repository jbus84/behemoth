import polars as pl
import numpy as np
import os
import lightgbm as lgb

def run_precision_tuning():
    print(">>> PRECISION TUNING (Seeking the Golden Threshold) <<<")
    
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
    
    # Triple Barrier Targets (Recalculate)
    ts_1m = df_1m["timestamp"].to_numpy()
    close_1m = df_1m[target].to_numpy()
    ts_15m = df_15m["timestamp"].to_numpy()
    
    target_barrier = np.zeros(len(df_15m), dtype=np.int32)
    start_indices = np.searchsorted(ts_1m, ts_15m)
    
    horizon_m = 60
    tp_bps = 20.0
    sl_bps = 10.0
    
    # We will also store the 'Realized PnL' (if we took the trade Long) for evaluation
    # This assumes we want to validate the "Long" signal. 
    # (Since we only trained on binary 0/1, let's focus on Long Precision first)
    trade_pnl_outcomes = np.zeros(len(df_15m)) # The result if we went Long
    
    for i, start_idx in enumerate(start_indices):
        if start_idx + horizon_m >= len(close_1m): 
            trade_pnl_outcomes[i] = 0
            continue
        
        entry = close_1m[start_idx]
        path = close_1m[start_idx+1 : start_idx + horizon_m + 1]
        changes = (path / entry - 1) * 10000
        
        hit_tp = np.where(changes > tp_bps)[0]
        hit_sl = np.where(changes < -sl_bps)[0]
        
        first_tp = hit_tp[0] if len(hit_tp) > 0 else 9999
        first_sl = hit_sl[0] if len(hit_sl) > 0 else 9999
        
        if first_tp < first_sl:
            target_barrier[i] = 1
            trade_pnl_outcomes[i] = tp_bps
        elif first_sl < first_tp:
            target_barrier[i] = 0
            trade_pnl_outcomes[i] = -sl_bps
        else:
            target_barrier[i] = 0
            trade_pnl_outcomes[i] = changes[-1] # Time exit
            
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
    
    # Map predictions to outcomes
    # Note: 'test' is a filtered dataframe, so we need to be careful with indices.
    # But since we built 'trade_pnl_outcomes' on df_15m, we can just slice it?
    # No, better to join or carry it.
    
    # Re-extract outcomes for test set
    test_outcomes = np.zeros(len(test))
    # We need to match indices. 
    # Let's just re-run the outcome logic for the test subset specifically to be safe
    # Or just rely on the fact that polars preserves order?
    # Yes, we can just filter the outcomes array same way.
    
    # Actually, let's just use the indices.
    # Or simpler:
    trade_outcomes_all = trade_pnl_outcomes
    is_test_mask = (df_15m["year"] > 2023).to_numpy()
    test_outcomes = trade_outcomes_all[is_test_mask]
    
    print("\n[PRECISION SWEEP (2024-2025 Test Set)]")
    print(f"{'Threshold':<10} | {'Trades':<8} | {'Win %':<8} | {'Gross':<8} | {'Net PnL':<8}")
    print("-" * 60)
    
    thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    
    for t in thresholds:
        signals = probs > t
        n_trades = np.sum(signals)
        
        if n_trades < 10:
            print(f"{t:<10.2f} | {n_trades:<8} | {'N/A':<8} | {'N/A':<8} | {'N/A':<8}")
            continue
            
        realized_pnls = test_outcomes[signals]
        avg_gross = np.mean(realized_pnls)
        avg_net = avg_gross - 1.5
        win_rate = np.mean(realized_pnls > 0)
        
        print(f"{t:<10.2f} | {n_trades:<8} | {win_rate:.1%}   | {avg_gross:<8.2f} | {avg_net:<8.2f}")

if __name__ == "__main__":
    run_precision_tuning()
