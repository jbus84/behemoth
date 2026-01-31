import polars as pl
import numpy as np
import os
import lightgbm as lgb

def run_pnl_by_year():
    print(">>> SNIPER STRATEGY: YEARLY BREAKDOWN <<<")
    
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
    
    # Targets
    ts_1m = df_1m["timestamp"].to_numpy()
    close_1m = df_1m[target].to_numpy()
    ts_15m = df_15m["timestamp"].to_numpy()
    
    target_barrier = np.zeros(len(df_15m), dtype=np.int32)
    trade_outcomes = np.zeros(len(df_15m))
    
    start_indices = np.searchsorted(ts_1m, ts_15m)
    horizon_m = 60
    tp_bps = 20.0
    sl_bps = 10.0
    
    for i, start_idx in enumerate(start_indices):
        if start_idx + horizon_m >= len(close_1m): continue
        entry = close_1m[start_idx]
        path = close_1m[start_idx+1 : start_idx + horizon_m + 1]
        changes = (path / entry - 1) * 10000
        
        hit_tp = np.where(changes > tp_bps)[0]
        hit_sl = np.where(changes < -sl_bps)[0]
        first_tp = hit_tp[0] if len(hit_tp) > 0 else 9999
        first_sl = hit_sl[0] if len(hit_sl) > 0 else 9999
        
        if first_tp < first_sl:
            target_barrier[i] = 1
            trade_outcomes[i] = tp_bps
        elif first_sl < first_tp:
            target_barrier[i] = 0
            trade_outcomes[i] = -sl_bps
        else:
            target_barrier[i] = 0
            trade_outcomes[i] = changes[-1]

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
    
    # Join outcomes manually
    is_test = (df_15m["year"] > 2023).to_numpy()
    outcomes_test = trade_outcomes[is_test]
    vol_test = df_15m.filter(pl.col("year") > 2023)["vol_1h"].to_numpy()
    years_test = df_15m.filter(pl.col("year") > 2023)["year"].to_numpy()
    
    # Vol Deciles (calculated on entire Test Set for fairness)
    vol_threshold = np.percentile(vol_test, 70) # D8+ (Top 30%)
    
    print(f"\nConfiguration: Vol > {vol_threshold:.2f} (D8+) | Prob > 0.80")
    print(f"{'Year':<6} | {'Trades':<8} | {'Win Rate':<10} | {'Net PnL':<10}")
    print("-" * 50)
    
    for y in [2024, 2025]:
        mask = (years_test == y) & (vol_test > vol_threshold) & (probs > 0.80)
        
        n_trades = np.sum(mask)
        if n_trades == 0:
            print(f"{y:<6} | 0        | N/A        | N/A")
            continue
            
        pnl = outcomes_test[mask]
        net_pnl = np.mean(pnl) - 1.5
        win_rate = np.mean(pnl > 0)
        
        print(f"{y:<6} | {n_trades:<8} | {win_rate:<10.1%} | {net_pnl:<10.2f} bps")

if __name__ == "__main__":
    run_pnl_by_year()
