import polars as pl
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score
import pandas as pd
import numpy as np

def train_positive_regime_model():
    input_file = "full_year_dataset_NSXUSD.parquet"
    print(f"Loading {input_file}...")
    
    try:
        df = pl.read_parquet(input_file)
    except Exception as e:
        print(f"Error loading data: {e}. Extraction might still be running.")
        return

    # Filter for Positive Regime
    df = df.filter(pl.col("regime_corr_1h") > 0)
    print(f"Positive Regime Samples: {len(df)}")
    
    if len(df) < 1000:
        print("Not enough data to train.")
        return
        
    # Features
    features = ["fx_ret_5s", "idx_vol_30s", "spread", "hour", "idx_ret_5s", "spread_chg_60s"]
    target = "target_trend" # 1 = Trend (Same Dir), 0 = Revert (Opp Dir)
    
    # Feature Engineering (Abs FX Ret for magnitude)
    df = df.with_columns([
        pl.col("fx_ret_5s").abs().alias("fx_ret_abs"),
        pl.col("idx_ret_5s").abs().alias("idx_mom_abs")
    ])
    
    features = ["fx_ret_abs", "idx_vol_30s", "spread", "hour", "idx_ret_5s", "spread_chg_60s"]
    
    # Convert to Pandas for LGBM
    X = df.select(features).to_pandas()
    y = df.select(target).to_pandas().values.ravel()
    
    # Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)
    
    # Train LGBM
    print("Training LightGBM...")
    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, max_depth=5, random_state=42)
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_prob)
    print(f"Model AUC: {auc:.4f}")
    
    # Feature Importance
    importances = pd.DataFrame({
        "Feature": features,
        "Importance": model.feature_importances_
    }).sort_values("Importance", ascending=False)
    print("\nFeature Importance:")
    print(importances)
    
    # Sniper Analysis
    # Can we find a high probability bucket?
    test_df = pd.DataFrame(X_test, columns=features)
    test_df["actual"] = y_test
    test_df["prob"] = y_pred_prob
    test_df["fwd_ret_bps"] = df.select("fwd_ret_bps").tail(len(y_test)).to_pandas().values.ravel()
    test_df["spread"] = df.select("spread").tail(len(y_test)).to_pandas().values.ravel()
    
    # Threshold Sweep
    print("\n--- SNIPER ANALYSIS ---")
    thresholds = [0.6, 0.65, 0.7, 0.75]
    for t in thresholds:
        # Long Trend (Pred > t)
        longs = test_df[test_df["prob"] > t]
        if len(longs) > 10:
            acc = accuracy_score(longs["actual"], [1]*len(longs))
            # EV Calculation
            # Win (1): Abs(Ret) - Spread
            # Loss (0): -Abs(Ret) - Spread
            wins = longs[longs["actual"] == 1]
            losses = longs[longs["actual"] == 0]
            
            avg_win = wins["fwd_ret_bps"].abs().mean() if len(wins) > 0 else 0
            avg_loss = losses["fwd_ret_bps"].abs().mean() if len(losses) > 0 else 0
            avg_spr = longs["spread"].mean()
            
            net_ev = (acc * (avg_win - avg_spr)) - ((1-acc) * (avg_loss + avg_spr))
            
            print(f"Prob > {t:.2f} | Count: {len(longs)} | Accuracy: {acc*100:.1f}% | Net EV: {net_ev:.2f} bps")
            
    # Check Reversion Snipers (Prob < 1-t)
    print("\n--- REVERSION SNIPERS ---")
    for t in thresholds:
        # Short Trend = Revert (Pred < 1-t)
        shorts = test_df[test_df["prob"] < (1-t)]
        if len(shorts) > 10:
            # We predict 0. Accuracy is "Is Actual == 0?"
            acc = accuracy_score(shorts["actual"], [0]*len(shorts))
            
            # EV
            wins = shorts[shorts["actual"] == 0]
            losses = shorts[shorts["actual"] == 1]
            
            avg_win = wins["fwd_ret_bps"].abs().mean() if len(wins) > 0 else 0
            avg_loss = losses["fwd_ret_bps"].abs().mean() if len(losses) > 0 else 0
            avg_spr = shorts["spread"].mean()
            
            net_ev = (acc * (avg_win - avg_spr)) - ((1-acc) * (avg_loss + avg_spr))
             
            print(f"Prob < {1-t:.2f} | Count: {len(shorts)} | Accuracy: {acc*100:.1f}% | Net EV: {net_ev:.2f} bps")

if __name__ == "__main__":
    train_positive_regime_model()
