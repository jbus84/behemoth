"""Trusted boosting scorer: purged/embargoed folds, complexity penalty, CatBoost
train->predict. CatBoost runs ONLY here (never in the sandbox)."""
from __future__ import annotations

import numpy as np


def purged_folds(n: int, k: int = 4, embargo: int = 50):
    """Contiguous-block K-fold with an embargo gap. Returns [(train_idx, val_idx)]; train
    excludes the val block plus `embargo` rows on each side (purged to avoid leakage from
    overlapping forward-return windows)."""
    idx = np.arange(n)
    bounds = np.linspace(0, n, k + 1).astype(int)
    folds = []
    for i in range(k):
        lo, hi = bounds[i], bounds[i + 1]
        val = idx[lo:hi]
        keep = np.ones(n, bool)
        keep[max(0, lo - embargo): min(n, hi + embargo)] = False
        folds.append((idx[keep], val))
    return folds


def complexity_penalty(n_feat: int, per_feature: float = 0.02) -> float:
    """Monotonic penalty subtracted from node value to punish large feature sets."""
    return per_feature * float(max(0, n_feat))


def train_predict(X_tr, y_tr, X_pred, *, seed: int = 0, depth: int = 4,
                  iterations: int = 200, lr: float = 0.05) -> np.ndarray:
    """Train a small, deterministic CatBoost regressor on (X_tr, y_tr); predict X_pred."""
    from catboost import CatBoostRegressor

    X_tr = np.nan_to_num(np.asarray(X_tr, float))
    y_tr = np.asarray(y_tr, float)
    fin = np.isfinite(y_tr)
    model = CatBoostRegressor(depth=depth, iterations=iterations, learning_rate=lr,
                              loss_function="RMSE", random_seed=seed, thread_count=1,
                              verbose=False)
    model.fit(X_tr[fin], y_tr[fin])
    return np.asarray(model.predict(np.nan_to_num(np.asarray(X_pred, float))), float)
