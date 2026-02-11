
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

DATA_DIR = "data/global_4h"

PAIRS = [
    ("FRXEUR", "BCOUSD"), # CAC/Oil
    ("XAUUSD", "BCOUSD"), # Gold/Oil
]

def train_ml_threshold():
    print("--- ML THRESHOLD FEASIBILITY STUDY (2018-2025) ---")

    features = []
    targets = []

    for y_sym, x_sym in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_4h.parquet")

        df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
        df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})

        df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

        y_log = np.log(df["Y"].to_numpy())
        x_log = np.log(df["X"].to_numpy())

        # Kalman
        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []

        for i in range(len(y_log)):
            if i < 10: mu_y, mu_x = y_log[i], x_log[i]
            else: mu_y, mu_x = np.mean(y_log[max(0,i-500):i]), np.mean(x_log[max(0,i-500):i])
            b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
            betas.append(b)
            errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))

        # Extract Trades
        in_pos = 0
        entry_idx = 0
        cost_bps = 9.0

        for i in range(500, len(y_log)):
            # Features at Entry
            # 1. Volatility
            vol_window = np.diff(y_log[i-50:i])
            vol = np.std(vol_window) * 1000

            # 2. Correlation
            ret_y = np.diff(y_log[i-50:i])
            ret_x = np.diff(x_log[i-50:i])
            if np.std(ret_x) > 1e-9 and np.std(ret_y) > 1e-9:
                corr = np.corrcoef(ret_x, ret_y)[0,1]
            else:
                corr = 0

            # 3. Z-Score Magnitude (The potential 'Choice')
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std

            # Simulate generic entry at Z > 1.5 (The "Opportunity")
            # We want to know if taking this trade was a good idea
            if in_pos == 0 and abs(z) > 1.5:
                # Potential Trade Logic
                # Look forward to find exit
                future_pnl = 0.0
                outcome = 0 # 0=Loss, 1=Win

                # Fast forward to next Z=0 or Stop
                for j in range(i+1, min(len(y_log), i+200)):
                    win_j = errors[j-500:j] # Recalc Z? Approximate using same mu/std for speed or update?
                    # For accuracy, we must use real Z sequence
                    # But we have 'errors' pre-calced. We just need to know if Z crosses 0.
                    # Wait, mu/std change. Let's assume static for 1-step lookahead or simple heuristic
                    # Let's use the actual pre-calced Z from loop?
                    # This script is linear... calculating Z each step in outer loop.
                    # Inner lookahead is expensive.
                    # Alternative: Strategy Simulation Mode.
                    pass

                # Simplified: Just mark the entry point and let the main loop handle exit.
                # When exit happens, record the trade with the Entry Features.

                if z > 1.5: in_pos = -1; entry_idx = i; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]; entry_feat = [vol, corr, abs(z)]
                elif z < -1.5: in_pos = 1; entry_idx = i; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]; entry_feat = [vol, corr, abs(z)]

            elif in_pos != 0:
                # Check for exit
                direction = 1 if in_pos == 1 else -1 # 1=Long, -1=Short
                # Long Exit: Z > 0 or Z < -3.5
                # Short Exit: Z < 0 or Z > 3.5

                exit_signal = False
                pnl = 0.0

                if in_pos == 1:
                    if z > 0.0: # Win
                        gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        exit_signal = True
                    elif z < -3.5: # Stop
                        gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        exit_signal = True
                else:
                    if z < 0.0: # Win
                        gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                        pnl = gross * 10000 - cost_bps
                        exit_signal = True
                    elif z > 3.5: # Stop
                         gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                         pnl = gross * 10000 - cost_bps
                         exit_signal = True

                if exit_signal:
                    features.append(entry_feat)
                    targets.append(1 if pnl > 0 else 0)
                    in_pos = 0

    print(f"Total Trades Collected: {len(targets)}")
    if len(targets) < 50:
        print("Not enough data for ML.")
        return

    # ML Training
    X = np.array(features)
    y = np.array(targets)

    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, shuffle=True)

    clf = RandomForestClassifier(n_estimators=100, max_depth=3, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, clf.predict_proba(X_test)[:,1])

    print(f"\n--- MODEL PERFORMANCE ---")
    print(f"Accuracy: {acc:.2f}")
    print(f"AUC:      {auc:.2f}")

    print("\n--- FEATURE IMPORTANCE ---")
    feat_names = ["Volatility", "Correlation", "Initial Z"]
    imps = clf.feature_importances_
    for name, imp in zip(feat_names, imps):
        print(f"{name}: {imp:.3f}")

    print("\n--- CLASSIFICATION REPORT ---")
    print(classification_report(y_test, y_pred))

if __name__ == "__main__":
    train_ml_threshold()
