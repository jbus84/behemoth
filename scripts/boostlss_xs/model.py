"""BoostLSS causal walk-forward model with Gaussian and GEV families.

Approach A: GaussianLSS (2 params: mu, sigma) — symmetric baseline.
Approach B: GEVLSS (3 params: mu, sigma, nu) — asymmetric tail family.
"""
from __future__ import annotations

import numpy as np
from boostlss_py import BoostLssModel, PyFamily, PyTreeLearner

# Parameters exposed by each distribution family
FAMILY_PARAMS: dict[str, list[str]] = {
    "GaussianLSS": ["mu", "sigma"],
    "GEVLSS": ["mu", "sigma", "nu"],
}

# Fixed hyperparameters — tune on fold 1 if needed
_MSTOP = 200
_STEP_LENGTH = 0.1
_MAX_DEPTH = 3
_N_FOLDS = 5


def _make_fold_boundaries(close_ts: np.ndarray, n_folds: int) -> list[tuple[int, int, int]]:
    """Return (train_end, test_start, test_end) index triples for expanding WFO.

    The series is split into n_folds+1 equal time blocks. Fold k uses blocks 0..k
    as train and block k+1 as test.
    """
    n = len(close_ts)
    block = n // (n_folds + 1)
    folds = []
    for k in range(n_folds):
        train_end = block * (k + 1)
        test_start = train_end
        test_end = min(block * (k + 2), n)
        folds.append((train_end, test_start, test_end))
    return folds


class BoostLssWFO:
    """Causal walk-forward BoostLSS model.

    For each fold: fit on train rows, predict on test rows.
    Assembles OOS predictions across all folds.
    """

    def __init__(self, family: str = "GEVLSS") -> None:
        if family not in FAMILY_PARAMS:
            raise ValueError(f"family must be one of {list(FAMILY_PARAMS)}, got {family!r}")
        self.family = family
        self.params = FAMILY_PARAMS[family]

    def _build_model(self, n_features: int) -> BoostLssModel:
        model = BoostLssModel(
            PyFamily(self.family),
            mstop=_MSTOP,
            step_length=_STEP_LENGTH,
        )
        all_feat_idx = list(range(n_features))
        for param in self.params:
            model.add_learner(param, PyTreeLearner(
                feature_indices=all_feat_idx,
                max_depth=_MAX_DEPTH,
            ))
        return model

    def fit_predict(
        self,
        X: np.ndarray,
        y: np.ndarray,
        close_ts: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Fit WFO, return OOS parameter predictions (NaN for train rows)."""
        n, n_features = X.shape
        oos_preds: dict[str, np.ndarray] = {p: np.full(n, np.nan) for p in self.params}

        folds = _make_fold_boundaries(close_ts, _N_FOLDS)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            X_train = X[:train_end].astype(np.float64)
            y_train = y[:train_end].astype(np.float64)
            X_test = X[test_start:test_end].astype(np.float64)

            # Drop NaN rows from training
            valid = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
            if valid.sum() < 100:
                continue

            model = self._build_model(n_features)
            model.fit(X_train[valid], y_train[valid])

            for param in self.params:
                pred = np.array(model.predict(X_test, param))
                oos_preds[param][test_start:test_end] = pred

            print(
                f"  Fold {fold_idx + 1}/{_N_FOLDS}: "
                f"train={valid.sum()} rows, test={test_end - test_start} rows"
            )

        return oos_preds
