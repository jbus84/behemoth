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
    "JSULSS": ["mu", "sigma", "nu", "tau"],
}

# Fixed hyperparameters
_MSTOP = 200
_STEP_LENGTH = 0.1
_MAX_DEPTH = 3
_N_FOLDS = 5
_MAX_TRAIN_ROWS = 20_000  # subsample per fold; None = use all rows


def _make_fold_boundaries(
    close_ts: np.ndarray, n_folds: int, embargo: int = 0
) -> list[tuple[int, int, int]]:
    """Return (train_end, test_start, test_end) index triples for expanding WFO."""
    n = len(close_ts)
    block = n // (n_folds + 1)
    folds = []
    for k in range(n_folds):
        train_end = block * (k + 1)
        test_start = min(train_end + embargo, block * (k + 2))
        test_end = min(block * (k + 2), n)
        folds.append((train_end, test_start, test_end))
    return folds


class BoostLssWFO:
    """Causal walk-forward BoostLSS model."""

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
        for param in self.params:
            model.add_learner(param, PyTreeLearner(
                feature_indices=list(range(n_features)),
                max_depth=_MAX_DEPTH,
            ))
        return model

    def fit_predict(
        self,
        X: np.ndarray,
        y: np.ndarray,
        close_ts: np.ndarray,
        embargo: int = 5,
    ) -> dict[str, np.ndarray]:
        """Fit WFO, return OOS parameter predictions (NaN for train rows)."""
        n, n_features = X.shape
        oos_preds: dict[str, np.ndarray] = {p: np.full(n, np.nan) for p in self.params}
        mu_threshold_per_row = np.full(n, np.nan)
        sigma_threshold_per_row = np.full(n, np.nan)

        folds = _make_fold_boundaries(close_ts, _N_FOLDS, embargo=embargo)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            X_train = X[:train_end].astype(np.float64)
            y_train = y[:train_end].astype(np.float64)
            X_test = X[test_start:test_end].astype(np.float64)

            valid = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
            if valid.sum() < 100:
                continue

            valid_idx = np.where(valid)[0]
            if _MAX_TRAIN_ROWS is not None and len(valid_idx) > _MAX_TRAIN_ROWS:
                rng = np.random.default_rng(42 + fold_idx)
                valid_idx = rng.choice(valid_idx, _MAX_TRAIN_ROWS, replace=False)
                valid_idx.sort()

            model = self._build_model(n_features)
            model.fit(X_train[valid_idx], y_train[valid_idx])

            for param in self.params:
                oos_preds[param][test_start:test_end] = np.array(
                    model.predict(X_test, param)
                )

            y_tr = y_train[valid_idx]
            mu_threshold_per_row[test_start:test_end] = 1.5 * max(
                float(np.nanmedian(np.abs(y_tr - np.nanmedian(y_tr)))), 1e-9
            )

            sigma_tr = np.array(model.predict(X_train[valid_idx], "sigma"))
            sigma_threshold_per_row[test_start:test_end] = float(
                np.nanpercentile(sigma_tr, 20)
            )

            print(
                f"    [{self.family} fold {fold_idx + 1}/{_N_FOLDS}] "
                f"train={len(valid_idx)} (of {valid.sum()} valid), "
                f"test={test_end - test_start}",
                flush=True,
            )

        oos_preds["mu_threshold_per_row"] = mu_threshold_per_row
        oos_preds["sigma_threshold_per_row"] = sigma_threshold_per_row
        return oos_preds
