import polars as pl
import pandas as pd
import lightgbm as lgb
import os
from sklearn.metrics import roc_auc_score, accuracy_score
import numpy as np

def train_regime_aware_model(idx_name):
    input_file = f"full_year_dataset_{idx_name}.parquet"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    df = pl.read_parquet(input_file).drop_nulls()
    print(f"\n--- Regime-Aware Training: {idx_name} ({len(df)} samples) ---")

    # Features: Include the new 'regime_corr_1h'
    features = ["fx_ret_5s", "idx_vol_30s", "spread", "hour", "regime_corr_1h"]
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    mapping = {name: i for i, name in enumerate(fx_pairs)}
    
    X_df = df.to_pandas()
    X_df['fx_pair_code'] = X_df['fx_pair'].map(mapping).fillna(-1).astype(int)
    
    # Target: target_trend (1 = Follow, 0 = Revert)
    y = X_df['target_trend'].values

    # Temporal Split (First 80% Train, Last 20% Test)
    split = int(len(X_df) * 0.8)
    X_train, X_test = X_df.iloc[:split].copy(), X_df.iloc[split:].copy()
    y_train, y_test = y[:split], y[split:]

    # Train
    cols = features # + ['fx_pair_code'] # fx_pair_code sometimes adds noise in general models
    # We include fx_pair_code as categorical
    
    clf = lgb.LGBMClassifier(
        n_estimators=200, 
        learning_rate=0.03, 
        max_depth=6, 
        verbose=-1, 
        importance_type='gain',
        random_state=42
    )
    
    clf.fit(X_train[cols + ['fx_pair_code']], y_train, categorical_feature=['fx_pair_code'])

    # Metrics
    y_prob = clf.predict_proba(X_test[cols + ['fx_pair_code']])[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, (y_prob > 0.5).astype(int))

    print(f"Dataset Split: Train={len(X_train)}, Test={len(X_test)}")
    print(f"Regime-Aware AUC: {auc:.4f}")
    print(f"Global Accuracy: {acc:.4f} (Baseline: {max(y_test.mean(), 1-y_test.mean()):.4f})")

    # Importance
    imps = pd.DataFrame({'Feature': cols + ['fx_pair_code'], 'Gain': clf.feature_importances_}).sort_values('Gain', ascending=False)
    print("\nFeature Importance (Gain):")
    print(imps)

    # Validate Regime Logic
    # Check if model learned to follow when correlation is positive and fade when negative
    # We can simluate this by checking the interaction
    
    test_df = X_test.copy()
    test_df['pred_prob'] = y_prob
    test_df['pred_class'] = (y_prob > 0.5).astype(int)
    
    print("\n--- Regime Analysis ---")
    # High Correlation Regime (> 0.2) -> Expect Trend (1)
    high_corr = test_df[test_df['regime_corr_1h'] > 0.2]
    # Low/Neg Correlation Regime (< -0.2) -> Expect Reversion (0)
    low_corr = test_df[test_df['regime_corr_1h'] < -0.2]
    
    if len(high_corr) > 0:
        print(f"High Corr Regime (>0.2): Model predicts TREND {test_df.loc[high_corr.index, 'pred_class'].mean():.1%} of time")
        print(f"Actual Outcome: {high_corr['target_trend'].mean():.1%} were TREND")
        
    if len(low_corr) > 0:
        print(f"Neg Corr Regime (<-0.2): Model predicts REVERT {(1-test_df.loc[low_corr.index, 'pred_class'].mean()):.1%} of time")
        print(f"Actual Outcome: {(1-low_corr['target_trend'].mean()):.1%} were REVERT")

def main():
    train_regime_aware_model("NSXUSD")

if __name__ == "__main__":
    main()
