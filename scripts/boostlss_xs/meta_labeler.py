"""HistGBM meta-labeler on OOS BoostLSS flags across all horizons."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

_HORIZONS = list(range(1, 6))  # N = 1, 2, 3, 4, 5
_META_THRESHOLD = 0.55
_N_FOLDS = 5


def _build_label(direction: np.ndarray, y: np.ndarray, threshold: float) -> np.ndarray:
    """Binary label: 1 if y * direction > threshold, else 0."""
    return ((y * direction) > threshold).astype(float)


def _build_meta_features(
    flags_by_horizon: dict[int, dict[str, np.ndarray]],
    direction: np.ndarray,
) -> np.ndarray:
    """Stack flag outputs across horizons into meta-feature matrix."""
    horizons = sorted(flags_by_horizon.keys())
    cols: list[np.ndarray] = []
    mu_flags: list[np.ndarray] = []

    for h in horizons:
        f = flags_by_horizon[h]
        _nan = np.full(len(f["mu_flag"]), np.nan)
        cols.extend([
            f["mu_flag"], f["mu_mag"],
            f["sigma_flag"], f["sigma_mag"],
            f["nu_flag"], f["nu_mag"],
            f.get("tau_flag", _nan), f.get("tau_mag", _nan),
        ])
        mu_flags.append(f["mu_flag"])

    # Horizon agreement: how many horizons fired mu_flag
    mu_stack = np.column_stack(mu_flags) if len(mu_flags) > 1 else mu_flags[0].reshape(-1, 1)
    horizon_agreement = np.nansum(mu_stack, axis=1).astype(float)
    cols.append(horizon_agreement)

    # mu+sigma co-fire at smallest horizon
    h_min = flags_by_horizon[horizons[0]]
    mu_sigma_agree = np.where(
        np.isnan(h_min["mu_flag"]) | np.isnan(h_min["sigma_flag"]),
        np.nan,
        (h_min["mu_flag"] * h_min["sigma_flag"]),
    )
    cols.append(mu_sigma_agree)

    # Direction
    cols.append(direction)

    mat = np.column_stack(cols)
    # Drop all-NaN columns so HistGBM binning doesn't fail on empty unique arrays
    # (e.g. tau_flag/tau_mag are all-NaN for GaussianLSS/GEVLSS families)
    keep = ~np.all(np.isnan(mat), axis=0)
    return mat[:, keep]


def _fold_boundaries(close_ts: np.ndarray, n_folds: int) -> list[tuple[int, int, int]]:
    n = len(close_ts)
    block = n // (n_folds + 1)
    return [
        (block * (k + 1), block * (k + 1), min(block * (k + 2), n))
        for k in range(n_folds)
    ]


class MetaLabeler:
    """HistGBM meta-labeler trained on OOS BoostLSS flags.

    WFO is aligned to the same fold boundaries as the BoostLSS model.
    Training data for fold k contains only OOS predictions from folds 1..k-1.
    """

    def __init__(self, threshold: float = _META_THRESHOLD) -> None:
        self.threshold = threshold

    def fit_predict(
        self,
        flags_by_horizon: dict[int, dict[str, np.ndarray]],
        y_by_horizon: dict[int, np.ndarray],
        direction: np.ndarray,
        symbols_arr: list[str],
        close_ts_arr: np.ndarray,
    ) -> np.ndarray:
        """Fit meta-labeler, return P(profitable) for OOS rows.

        Returns array of length N; NaN for train rows.
        """
        n = len(direction)
        meta_X = _build_meta_features(flags_by_horizon, direction)

        # Build label using smallest horizon as primary, per-symbol median threshold
        h_primary = min(y_by_horizon.keys())
        y1 = y_by_horizon[h_primary]
        symbols = np.array(symbols_arr)

        probs = np.full(n, np.nan)
        folds = _fold_boundaries(close_ts_arr, _N_FOLDS)

        for fold_idx, (train_end, test_start, test_end) in enumerate(folds):
            if fold_idx == 0:
                # No OOS predictions available yet to train meta-labeler on
                continue

            # Build labels for training rows (only OOS rows from previous folds)
            # First fold's test rows are the earliest OOS predictions available
            first_oos_start = folds[0][1]
            train_meta_end = train_end

            X_meta_train = meta_X[first_oos_start:train_meta_end]
            y1_train = y1[first_oos_start:train_meta_end]
            dir_train = direction[first_oos_start:train_meta_end]
            sym_train = symbols[first_oos_start:train_meta_end]

            # Per-symbol median |return| threshold, computed on train window
            thresholds: dict[str, float] = {}
            for sym in np.unique(sym_train):
                mask = sym_train == sym
                y_sym = y1_train[mask]
                valid = y_sym[~np.isnan(y_sym)]
                thresholds[sym] = float(np.median(np.abs(valid))) if len(valid) > 0 else 0.0

            # Build per-row thresholds
            row_thresh = np.array([thresholds.get(s, 0.0) for s in sym_train])
            labels = _build_label(dir_train, y1_train, row_thresh)

            # Drop rows where direction or label target is NaN
            # (HistGBM handles NaN feature values natively)
            valid_mask = ~(np.isnan(dir_train) | np.isnan(y1_train))
            if valid_mask.sum() < 20:
                continue

            clf = HistGradientBoostingClassifier(
                max_iter=100, learning_rate=0.05, max_depth=3, random_state=42
            )
            clf.fit(X_meta_train[valid_mask], labels[valid_mask])

            X_test = meta_X[test_start:test_end]
            dir_test = direction[test_start:test_end]
            valid_test = ~np.isnan(dir_test)
            if valid_test.sum() == 0:
                continue

            test_probs = np.full(test_end - test_start, np.nan)
            test_probs[valid_test] = clf.predict_proba(X_test[valid_test])[:, 1]
            probs[test_start:test_end] = test_probs

        return probs
