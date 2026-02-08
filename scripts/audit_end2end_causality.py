#!/usr/bin/env python3
"""
End-to-end causality audit: Kalman -> features -> CatBoost predictions.

Checks whether predictions at time i remain unchanged when future data is perturbed.
"""

import os
import sys
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor, CatBoostClassifier

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from build_meta_dataset_v3_h1 import compute_kalman_states, compute_z_scores, compute_features_at_entry

FEATURE_NAMES = [
    'active_leg', 'side',
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'signal_beta_lookback', 'hedge_beta_lookback', 'beta_mismatch',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_16b', 'ret_Y_16b', 'atr_ratio', 'entry_atr', 'vol_regime'
]


def load_pair(y_sym, x_sym, n_tail=6000):
    p_y = f"data/global_1h/{y_sym}_1h.parquet"
    p_x = f"data/global_1h/{x_sym}_1h.parquet"
    if not os.path.exists(p_y) or not os.path.exists(p_x):
        raise FileNotFoundError(f"Missing data for {y_sym} or {x_sym}")

    df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
    df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")
    if len(df) > n_tail:
        df = df.tail(n_tail)

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()
    return df, y, x, ts


def predict_from_features(clf, reg, feat):
    z = feat['z_entry']
    beta = feat['beta']

    if 0.98 <= beta <= 1.02:
        return ('WAIT', None)

    active_leg = 'Y' if beta < 0.98 else 'X'

    if z > 1.5:
        side = 'LONG'
    elif z < -1.5:
        side = 'SHORT'
    else:
        return ('WAIT', None)

    row = {**feat, 'active_leg': active_leg, 'side': side}
    model_features = list(getattr(reg, "feature_names_", [])) or FEATURE_NAMES
    X = pd.DataFrame([row])[model_features]
    pred = float(reg.predict(X)[0])
    p_up = float(clf.predict_proba(X)[0][1])
    if p_up >= 0.5 and pred > 20.0:
        return ('TRADE', (pred, p_up, side, active_leg))
    return ('WAIT', None)


def main():
    y_sym = os.environ.get("Y_SYM", "XAUUSD")
    x_sym = os.environ.get("X_SYM", "BCOUSD")
    samples = int(os.environ.get("SAMPLES", "20"))
    seed = int(os.environ.get("SEED", "13"))

    reg_path = "models/meta_model_h1/catboost_h1_reg.cbm"
    clf_path = "models/meta_model_h1/catboost_h1_clf.cbm"
    reg = CatBoostRegressor()
    reg.load_model(reg_path)
    clf = CatBoostClassifier()
    clf.load_model(clf_path)

    df, y, x, ts = load_pair(y_sym, x_sym)
    n = len(y)

    rng = np.random.default_rng(seed)
    idxs = rng.integers(700, n - 200, size=samples)

    # Base states
    betas, errors, ret_betas = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    pred_changes = 0
    decision_changes = 0

    for i in idxs:
        feat = compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts)
        dec, sig = predict_from_features(clf, reg, feat)

        # Perturb future only
        y2 = y.copy()
        x2 = x.copy()
        y2[i + 1:] += rng.normal(0.0, 0.05, size=n - i - 1)
        x2[i + 1:] += rng.normal(0.0, 0.05, size=n - i - 1)

        betas2, errors2, ret_betas2 = compute_kalman_states(y2, x2)
        z_scores2 = compute_z_scores(errors2)
        feat2 = compute_features_at_entry(i, y2, x2, betas2, errors2, ret_betas2, z_scores2, ts)

        dec2, sig2 = predict_from_features(clf, reg, feat2)

        if dec != dec2:
            decision_changes += 1

        if (sig is None) != (sig2 is None):
            pred_changes += 1
        elif sig is not None and sig2 is not None:
            if abs(sig[0] - sig2[0]) > 1e-6 or sig[1:] != sig2[1:]:
                pred_changes += 1

    print(f"End-to-end causality audit on {y_sym}/{x_sym} | bars={n} | samples={samples}")
    print(f"Decision changes: {decision_changes} / {samples}")
    print(f"Prediction changes: {pred_changes} / {samples}")


if __name__ == "__main__":
    main()
