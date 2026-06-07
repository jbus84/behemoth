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
                  iterations: int = 200, lr: float = 0.05, k_folds: int = 4,
                  embargo: int = 50) -> np.ndarray:
    """Purged K-fold cross-fitted CatBoost ensemble: train one small regressor per fold on
    the purged+embargoed complement of that fold, then average the K models' predictions on
    X_pred. The purging removes rows within `embargo` of each held-out block so overlapping
    forward-return windows don't leak into a fold's training set. Deterministic (fixed seed,
    thread_count=1). Falls back to a single full-data fit if folds are too thin."""
    from catboost import CatBoostRegressor

    X_tr = np.nan_to_num(np.asarray(X_tr, float))
    y_tr = np.asarray(y_tr, float)
    fin = np.isfinite(y_tr)
    Xf, yf = X_tr[fin], y_tr[fin]  # trailing NaN-label rows dropped; Xf stays time-contiguous
    Xp = np.nan_to_num(np.asarray(X_pred, float))

    def _fit(Xt, yt, s):
        m = CatBoostRegressor(depth=depth, iterations=iterations, learning_rate=lr,
                              loss_function="RMSE", random_seed=s, thread_count=1,
                              verbose=False)
        m.fit(Xt, yt)
        return np.asarray(m.predict(Xp), float)

    if len(Xf) < max(200, 4 * embargo) or k_folds < 2:
        return _fit(Xf, yf, seed)

    preds = np.zeros(len(Xp))
    used = 0
    for i, (tr_idx, _val) in enumerate(purged_folds(len(Xf), k=k_folds, embargo=embargo)):
        if len(tr_idx) < 50:
            continue
        preds += _fit(Xf[tr_idx], yf[tr_idx], seed + i)
        used += 1
    return preds / used if used else _fit(Xf, yf, seed)
