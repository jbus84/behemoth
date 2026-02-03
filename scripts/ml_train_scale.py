
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
import joblib

DATA_DIR = "data/global_1h"

# Mix of Tier 1, 2, and 3 for variety
PAIRS = [
    ("FRXEUR", "BCOUSD"),
    ("XAUUSD", "BCOUSD"),
    ("USDCHF", "GRXEUR"), # Dead pair - good for negatives
    ("FRXEUR", "EURGBP"),
    ("UDXUSD", "GRXEUR"),
    ("FRXEUR", "USDJPY"),
    ("EURUSD", "EURJPY"),
    ("BCOUSD", "XAGUSD"),
    ("XAUUSD", "NSXUSD"), # Tier 3
    ("EURUSD", "AUDUSD"), # Tier 3
]

def train_ml_scale():
    print(f"--- BIG DATA ML TRAINING (10 PAIRS, 8 YEARS, H1) ---")
    
    features = []
    targets = []
    
    total_trades = 0
    
    for y_sym, x_sym in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_1h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_1h.parquet")
        
        if not os.path.exists(p_y) or not os.path.exists(p_x): continue
        
        try:
            df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
            df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})
            
            df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
            
            y_log = np.log(df["Y"].to_numpy())
            x_log = np.log(df["X"].to_numpy())
            ts = df["timestamp"].to_numpy()
            
            # Kalman
            kf = KalmanFilterReg(Q=1e-5, R=1e-3)
            betas, errors = [], []
            
            for i in range(len(y_log)):
                if i < 10: mu_y, mu_x = y_log[i], x_log[i]
                else: mu_y, mu_x = np.mean(y_log[max(0,i-500):i]), np.mean(x_log[max(0,i-500):i])
                b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
                betas.append(b)
                errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))
                
            in_pos = 0
            entry_idx = 0
            cost_bps = 9.0
            entry_feat = []
            
            # Use Z > 1.0 to get looser samples (negatives)
            THRESH = 1.0
            STOP = 3.5
            
            for i in range(500, len(y_log)):
                # Features
                if i > 50:
                    vol_window = np.diff(y_log[i-50:i])
                    vol = np.std(vol_window) * 1000
                    
                    ret_y = np.diff(y_log[i-50:i])
                    ret_x = np.diff(x_log[i-50:i])
                    if np.std(ret_x) > 1e-9 and np.std(ret_y) > 1e-9:
                        corr = np.corrcoef(ret_x, ret_y)[0,1]
                    else:
                        corr = 0
                else:
                    vol = 0; corr = 0
                
                # Z-Score
                window = errors[i-500:i]
                mu, std = np.mean(window), np.std(window)
                if std < 1e-6: continue
                z = (errors[i] - mu) / std
                
                # Entry Logic
                if in_pos == 0:
                    if abs(z) > THRESH:
                        # Capture Entry
                        feat = [vol, corr, abs(z)]
                        if z > THRESH: in_pos = -1
                        else: in_pos = 1
                        
                        entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]; entry_feat = feat
                        
                elif in_pos != 0:
                    exit_signal = False
                    pnl = 0.0
                    
                    if in_pos == 1: # Long
                        if z > 0.0: # Win
                            gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                            pnl = gross * 10000 - cost_bps
                            exit_signal = True
                        elif z < -STOP: # Stop
                            gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                            pnl = gross * 10000 - cost_bps
                            exit_signal = True
                    elif in_pos == -1: # Short
                        if z < 0.0: # Win
                            gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                            pnl = gross * 10000 - cost_bps
                            exit_signal = True
                        elif z > STOP: # Stop
                             gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                             pnl = gross * 10000 - cost_bps
                             exit_signal = True
                    
                    if exit_signal:
                        features.append(entry_feat)
                        # We want to predict PROFITABLE trades
                        # Label 1 if PnL > 0, else 0
                        targets.append(1 if pnl > 0 else 0)
                        in_pos = 0
                        total_trades += 1
                        
        except Exception as e:
            print(f"Error {y_sym}/{x_sym}: {e}")

    print(f"Total Trades Collected: {total_trades}")
    
    if total_trades < 100:
        print("Still not enough data.")
        return

    # ML Training
    X = np.array(features)
    y = np.array(targets)
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=True)
    
    clf = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=42)
    clf.fit(X_train, y_train)
    
    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:,1]
    
    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_prob)
    
    print(f"\n--- MODEL PERFORMANCE ---")
    print(f"Accuracy: {acc:.2f}")
    print(f"AUC:      {auc:.2f}")
    
    print("\n--- FEATURE IMPORTANCE ---")
    feat_names = ["Volatility", "Correlation", "Initial Z"]
    imps = clf.feature_importances_
    for name, imp in zip(feat_names, imps):
        print(f"{name}: {imp:.3f}")
        
    print("\n--- PROBABILITY CALIBRATION ---")
    # Check if high prob implies high win rate
    high_conf = y_prob > 0.7
    if np.sum(high_conf) > 0:
        win_rate_high = np.mean(y_test[high_conf])
        print(f"Win Rate when Prob > 0.7: {win_rate_high*100:.1f}% (Count: {np.sum(high_conf)})")
    else:
        print("No high confidence predictions.")

if __name__ == "__main__":
    train_ml_scale()
