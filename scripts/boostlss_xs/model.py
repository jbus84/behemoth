"""XGBoostLSS causal walk-forward model.

Approach A: Gaussian  (2 params: mu, sigma) — symmetric baseline.
Approach B: StudentT  (3 params: mu, sigma, nu) — fat-tail family; low nu = heavy tail.

XGBoostLSS replaces boostlss_py for ~2000× speed improvement (multi-threaded XGBoost
vs single-threaded Rust; 0.2s vs 7min per fold on 20k rows × 30 features).
"""
from __future__ import annotations

import numpy as np
import xgboost as xgb
from xgboostlss.distributions.Gaussian import Gaussian
from xgboostlss.distributions.StudentT import StudentT
from xgboostlss.model import XGBoostLSS

# Internal param names (downstream flagging uses these)
FAMILY_PARAMS: dict[str, list[str]] = {
    "Gaussian": ["mu", "sigma"],
    "StudentT": ["mu", "sigma", "nu"],
}

# XGBoostLSS param name → our internal name
_PARAM_RENAME: dict[str, dict[str, str]] = {
    "Gaussian": {"loc": "mu", "scale": "sigma"},
    "StudentT": {"loc": "mu", "scale": "sigma", "df": "nu"},
}

# Fixed hyperparameters
_NUM_BOOST_ROUND = 200
_XGB_PARAMS = {
    "eta": 0.1,
    "max_depth": 3,
    "verbosity": 0,
    "nthread": -1,
}
_N_FOLDS = 5
_MAX_TRAIN_ROWS = 20_000  # subsample per fold; None = use all rows


def _make_distribution(family: str) -> Gaussian | StudentT:
    if family == "Gaussian":
        return Gaussian(stabilization="None", response_fn="softplus", loss_fn="nll")
    if family == "StudentT":
        return StudentT(stabilization="None", response_fn="softplus", loss_fn="nll")
    raise ValueError(f"Unknown family {family!r}")


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
    """Causal walk-forward XGBoostLSS model.

    Same interface as before: fit on train rows, predict on test rows,
    return OOS parameter dict with NaN for train rows.
    """

    def __init__(self, family: str = "StudentT") -> None:
        if family not in FAMILY_PARAMS:
            raise ValueError(f"family must be one of {list(FAMILY_PARAMS)}, got {family!r}")
        self.family = family
        self.params = FAMILY_PARAMS[family]

    def fit_predict(
        self,
        X: np.ndarray,
        y: np.ndarray,
        close_ts: np.ndarray,
        embargo: int = 5,
    ) -> dict[str, np.ndarray]:
        """Fit WFO, return OOS parameter predictions (NaN for train rows).

        Per-fold thresholds are returned as per-row arrays to avoid look-ahead.
        """
        n, n_features = X.shape
        oos_preds: dict[str, np.ndarray] = {p: np.full(n, np.nan) for p in self.params}
        mu_threshold_per_row = np.full(n, np.nan)
        sigma_threshold_per_row = np.full(n, np.nan)
        rename = _PARAM_RENAME[self.family]

        folds = _make_fold_boundaries(close_ts, _N_FOLDS, embargo=embargo)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            X_train = X[:train_end].astype(np.float32)
            y_train = y[:train_end].astype(np.float32)
            X_test = X[test_start:test_end].astype(np.float32)

            valid = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
            if valid.sum() < 100:
                continue

            valid_idx = np.where(valid)[0]
            if _MAX_TRAIN_ROWS is not None and len(valid_idx) > _MAX_TRAIN_ROWS:
                rng = np.random.default_rng(42 + fold_idx)
                valid_idx = rng.choice(valid_idx, _MAX_TRAIN_ROWS, replace=False)
                valid_idx.sort()

            dtrain = xgb.DMatrix(X_train[valid_idx], label=y_train[valid_idx])
            dtest = xgb.DMatrix(X_test)

            model = XGBoostLSS(_make_distribution(self.family))
            model.train(_XGB_PARAMS, dtrain, num_boost_round=_NUM_BOOST_ROUND, verbose_eval=False)

            pred_df = model.predict(dtest)
            for xgb_name, our_name in rename.items():
                oos_preds[our_name][test_start:test_end] = pred_df[xgb_name].to_numpy()

            # Per-fold thresholds from training labels only
            y_tr = y_train[valid_idx]
            fold_mu_threshold = 1.5 * max(
                float(np.nanmedian(np.abs(y_tr - np.nanmedian(y_tr)))), 1e-9
            )
            mu_threshold_per_row[test_start:test_end] = fold_mu_threshold

            # sigma threshold: 20th pctile of training-fold sigma predictions
            dtrain_full = xgb.DMatrix(X_train[valid_idx])
            sigma_tr = model.predict(dtrain_full)["scale"].to_numpy()
            sigma_threshold_per_row[test_start:test_end] = float(np.nanpercentile(sigma_tr, 20))

            print(
                f"  Fold {fold_idx + 1}/{_N_FOLDS}: "
                f"train={len(valid_idx)} (of {valid.sum()} valid), "
                f"test={test_end - test_start}"
            )

        oos_preds["mu_threshold_per_row"] = mu_threshold_per_row
        oos_preds["sigma_threshold_per_row"] = sigma_threshold_per_row
        return oos_preds
