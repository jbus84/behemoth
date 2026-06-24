"""Purged K-Fold cross-validation (Lopez de Prado AFML ch.7) for overlapping labels.

Test folds are contiguous blocks of (time-sorted) events. Train observations whose
label interval [entry, t1] overlaps a test fold's bar interval are PURGED, and an
EMBARGO drops train observations starting just after the test interval. This is the
data-efficient CV for model tuning; the final P&L gate stays walk-forward (live-like).

Self-test: `uv run python scripts/fx_coint/purged_kfold.py`
"""
from __future__ import annotations

import numpy as np
from scipy import stats
from sklearn.base import clone


class PurgedKFold:
    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, entry: np.ndarray, t1: np.ndarray):
        entry = np.asarray(entry)
        t1 = np.asarray(t1)
        n = len(entry)
        n_bars = int(t1.max()) + 1
        embargo = int(n_bars * self.embargo_pct)
        idx = np.arange(n)
        bounds = np.linspace(0, n, self.n_splits + 1, dtype=int)
        for k in range(self.n_splits):
            te = idx[bounds[k]:bounds[k + 1]]
            if len(te) == 0:
                continue
            t_lo = entry[te].min()
            t_hi = t1[te].max()
            # purge: drop train whose [entry, t1] intersects [t_lo, t_hi]
            overlap = (entry <= t_hi) & (t1 >= t_lo)
            # embargo: drop train starting within `embargo` bars after t_hi
            embargoed = (entry > t_hi) & (entry <= t_hi + embargo)
            train_mask = ~overlap & ~embargoed
            train_mask[te] = False
            yield idx[train_mask], te


def ic_scorer(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman Information Coefficient (rank correlation), NaN-safe.

    Args:
        y_true: Target values.
        y_pred: Predicted values.

    Returns:
        Spearman rank correlation. Returns 0.0 if degenerate (< 10 finite pairs or < 3 unique predictions).
    """
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(yt) & np.isfinite(yp)
    if ok.sum() < 10 or np.unique(yp[ok]).size < 3:
        return 0.0
    r = stats.spearmanr(yt[ok], yp[ok])[0]
    return float(r) if np.isfinite(r) else 0.0


def purged_cv_score(estimator, X, y, entry, t1, sample_weight=None,
                    n_splits=5, embargo_pct=0.01) -> np.ndarray:
    """Purged K-Fold cross-validation score using IC scorer.

    Clones and fits the estimator on each purged train fold (passing sample_weight if given),
    scores using ic_scorer on the test fold, and returns per-fold score array.
    NaN rows in X/y are dropped per fold.

    Args:
        estimator: sklearn estimator with fit() and predict() methods.
        X: Feature matrix (n, p).
        y: Target vector (n,).
        entry: Entry bar indices (n,).
        t1: Exit bar indices (n,).
        sample_weight: Optional sample weights (n,).
        n_splits: Number of folds (default 5).
        embargo_pct: Embargo as fraction of max bar index (default 0.01).

    Returns:
        Array of per-fold IC scores. If no valid folds, returns [np.nan].
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    pk = PurgedKFold(n_splits=n_splits, embargo_pct=embargo_pct)
    scores = []
    for tr, te in pk.split(entry, t1):
        okt = np.isfinite(X[tr]).all(1) & np.isfinite(y[tr])
        oke = np.isfinite(X[te]).all(1) & np.isfinite(y[te])
        if okt.sum() < 50 or oke.sum() < 20:
            continue
        est = clone(estimator)
        if sample_weight is not None:
            est.fit(X[tr][okt], y[tr][okt], sample_weight=np.asarray(sample_weight)[tr][okt])
        else:
            est.fit(X[tr][okt], y[tr][okt])
        scores.append(ic_scorer(y[te][oke], est.predict(X[te][oke])))
    return np.array(scores) if scores else np.array([np.nan])


def _self_test() -> None:
    entry = np.arange(100)
    t1 = entry + 3
    pk = PurgedKFold(n_splits=5, embargo_pct=0.02)
    for tr, te in pk.split(entry, t1):
        print("train", len(tr), "test", len(te))


if __name__ == "__main__":
    _self_test()
