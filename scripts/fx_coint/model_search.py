"""Signed-return regression model ladder + driver.

Predicts mu = expected signed first-touch return (bps); trade sign(mu), select/size
by |mu|. Ladder (each must beat the one below on walk-forward net-bps):
  ridge -> ridge+interactions (design matrix) -> histgbm -> bagged-histgbm (seq boot).
Tuned/compared with PurgedKFold + return-attribution weights; final gate = walk-forward
non-overlap net-bps vs the fixed base.

Usage: uv run python scripts/fx_coint/model_search.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_weights import seq_bootstrap  # noqa: E402


def build_design(f, ev, feature_names, interactions):
    """Stack design matrix from features, optionally append interaction columns.

    Args:
        f: dict mapping feature name -> np.ndarray (per-bar values)
        ev: np.ndarray, event indices to select from f
        feature_names: list[str], names of columns to include
        interactions: list[tuple[str, str]], pairs of feature names to multiply

    Returns:
        (X, names): (np.ndarray of shape (len(ev), len(feature_names) + len(interactions)),
                     list[str] of column names)
    """
    cols = [f[name][ev] for name in feature_names]
    names = list(feature_names)
    for a, b in interactions:
        cols.append(f[a][ev] * f[b][ev])
        names.append(f"{a}*{b}")
    return np.column_stack(cols), names


def _histgbm(seed=0):
    """Regularized HistGradientBoostingRegressor for signed returns."""
    return HistGradientBoostingRegressor(
        max_depth=4, max_iter=200, learning_rate=0.05, l2_regularization=1.0,
        min_samples_leaf=50, early_stopping=False,
        random_state=seed)


class _BaggedHistGBM:
    """Bagged HistGBM using sequential bootstrap for resampling.

    Fits n_bags HistGBMs on sequential-bootstrap resamples and averages predictions.
    If entry/t1 provided during fit, uses seq_bootstrap; else falls back to uniform.
    """
    def __init__(self, n_bags=10, seed=0):
        self.n_bags = n_bags
        self.seed = seed
        self.models_ = []

    def fit(self, X, y, sample_weight=None, entry=None, t1=None):
        """Fit n_bags models on bootstrap resamples.

        Args:
            X: feature matrix (n_samples, n_features)
            y: target vector (n_samples,)
            sample_weight: optional per-sample weights
            entry: optional event entry bar indices (enables seq_bootstrap)
            t1: optional event end bar indices (enables seq_bootstrap)

        Returns:
            self
        """
        rng = np.random.default_rng(self.seed)
        n = len(y)
        self.models_ = []
        for b in range(self.n_bags):
            if entry is not None and t1 is not None:
                draw = seq_bootstrap(np.asarray(entry), np.asarray(t1), n_draws=n,
                                     rng=np.random.default_rng(self.seed + b))
            else:
                draw = rng.integers(0, n, n)
            m = _histgbm(self.seed + b)
            sw = None if sample_weight is None else np.asarray(sample_weight)[draw]
            m.fit(X[draw], y[draw], sample_weight=sw)
            self.models_.append(m)
        return self

    def predict(self, X):
        """Average predictions across all bagged models."""
        return np.mean([m.predict(X) for m in self.models_], axis=0)


def make_models(seed=0):
    """Create model ladder: ridge, histgbm, bagged_histgbm.

    Returns:
        dict with keys ["ridge", "histgbm", "bagged_histgbm"], each a fitted-ready regressor.
    """
    return {"ridge": Ridge(alpha=10.0),
            "histgbm": _histgbm(seed),
            "bagged_histgbm": _BaggedHistGBM(n_bags=10, seed=seed)}


def main():
    """Placeholder for driver code (added in Task 6)."""
    pass


if __name__ == "__main__":
    main()
