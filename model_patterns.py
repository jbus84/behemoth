import polars as pl
import pandas as pd
import numpy as np
import lightgbm as lgb
import os
from sklearn.metrics import roc_auc_score, accuracy_score

def train_and_discover(idx_name):
    input_file = f"lead_lag_patterns_{idx_name}.parquet"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    df = pl.read_parquet(input_file).drop_nulls()
    print(f"\n--- Pattern Discovery: {idx_name} ({len(df)} samples) ---")

    # Features
    features = ["fx_ret_5s", "idx_vol_30s", "spread", "hour", "minute"]
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    mapping = {name: i for i, name in enumerate(fx_pairs)}
    
    X_df = df.to_pandas()
    X_df['fx_pair_code'] = X_df['fx_pair'].map(mapping).fillna(-1).astype(int)
    y = X_df['target'].values

    # Temporal Split
    split = int(len(X_df) * 0.8)
    X_train, X_test = X_df.iloc[:split].copy(), X_df.iloc[split:].copy()
    y_train, y_test = y[:split], y[split:]

    # Train
    cols = features + ['fx_pair_code']
    clf = lgb.LGBMClassifier(
        n_estimators=100, 
        learning_rate=0.05, 
        max_depth=5, 
        verbose=-1, 
        importance_type='gain',
        random_state=42
    )
    clf.fit(X_train[cols], y_train, categorical_feature=['fx_pair_code'])

    # Metrics
    y_prob = clf.predict_proba(X_test[cols])[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, (y_prob > 0.5).astype(int))

    print(f"Predictability (AUC): {auc:.4f}")
    print(f"Strategy Accuracy: {acc:.4f} (Against Momentum: {1-y_test.mean():.4f})")

    # Importance
    imps = pd.DataFrame({'Feature': cols, 'Gain': clf.feature_importances_}).sort_values('Gain', ascending=False)
    print("\nTop Predictive Factors (Gain):")
    print(imps.head(5))

    # Pattern Rules
    print("\nAlpha Rule Extraction:")
    test_pl = df.slice(split).with_columns(pred=pl.Series(y_prob))
    
    # Rule 1: High Intensity Bursts
    big_burst = test_pl.filter(pl.col("fx_ret_5s").abs() > 4.0)
    if len(big_burst) > 10:
        wr = (big_burst["target"] == 0).mean()
        print(f"* MOMENTUM EXHAUSTION: FX Burst > 4bps => {idx_name} Reversion Prob: {wr:.1%}")

    # Rule 2: USDJPY specific
    jpy_rule = test_pl.filter(pl.col("fx_pair") == "USDJPY")
    if len(jpy_rule) > 10:
        wr = (jpy_rule["target"] == 0).mean()
        print(f"* YEN SENTIMENT FADE: USDJPY Burst => {idx_name} Reversion Prob: {wr:.1%}")

    # Rule 3: Low-Vol Timing
    low_vol = test_pl.filter(pl.col("idx_vol_30s") < 0.5)
    if len(low_vol) > 10:
        wr = (low_vol["target"] == 0).mean()
        print(f"* LOW-VOL REVERSION: FX Burst @ Quiet Market => {idx_name} Reversion Prob: {wr:.1%}")

def main():
    for idx_name in ["NSXUSD", "SPXUSD"]:
        train_and_discover(idx_name)

if __name__ == "__main__":
    main()
