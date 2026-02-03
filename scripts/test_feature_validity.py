#!/usr/bin/env python3
"""
Feature validity tests for the H1 meta model.

Tests:
1) No future leakage: features at index i must be identical even if future data changes.
2) Inference feature parity: inference feature computation matches training feature logic.
"""

import numpy as np
import polars as pl
from datetime import datetime, timedelta

from build_meta_dataset_v3_h1 import (
    compute_kalman_states,
    compute_z_scores,
    compute_features_at_entry,
)
from inference_meta_model import MetaModelInference


def _make_series(n=800, seed=42):
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.normal(0, 0.01, n)) + 4.0  # log price
    y = 1.1 * x + rng.normal(0, 0.01, n)         # correlated log price
    return y, x


def _make_timestamps(n=800):
    start = datetime(2020, 1, 1)
    return np.array([start + timedelta(hours=i) for i in range(n)], dtype="datetime64[ns]")


def _assert_close(a, b, tol=1e-6, label="value"):
    if not np.isfinite(a) and not np.isfinite(b):
        return
    if abs(a - b) > tol:
        raise AssertionError(f"Mismatch for {label}: {a} vs {b} (tol={tol})")


def test_no_future_leakage():
    y, x = _make_series()
    ts = _make_timestamps(len(y))

    betas, errors = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    i = 700
    feat_orig = compute_features_at_entry(i, y, x, betas, errors, z_scores, ts)

    # Modify future values only
    y2 = y.copy()
    x2 = x.copy()
    y2[i + 1:] += 0.5
    x2[i + 1:] -= 0.3

    betas2, errors2 = compute_kalman_states(y2, x2)
    z_scores2 = compute_z_scores(errors2)

    # Causality checks
    if not np.allclose(betas[: i + 1], betas2[: i + 1], atol=1e-9):
        raise AssertionError("Betas changed before index i when only future data changed.")
    if not np.allclose(errors[: i + 1], errors2[: i + 1], atol=1e-9):
        raise AssertionError("Errors changed before index i when only future data changed.")
    if not np.allclose(z_scores[: i + 1], z_scores2[: i + 1], atol=1e-9):
        raise AssertionError("Z-scores changed before index i when only future data changed.")

    feat_new = compute_features_at_entry(i, y2, x2, betas2, errors2, z_scores2, ts)

    for k in feat_orig.keys():
        _assert_close(feat_orig[k], feat_new[k], tol=1e-6, label=k)

    print("[PASS] test_no_future_leakage")


def test_inference_feature_parity():
    y, x = _make_series()
    ts = _make_timestamps(len(y))

    betas, errors = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    # Build raw closes for inference (inference logs them internally)
    df = pl.DataFrame({
        "timestamp": ts,
        "close_X": np.exp(x),
        "close_Y": np.exp(y),
    })

    inf = MetaModelInference(load_model=False)
    pdf = inf._compute_features(df, betas, errors, z_scores)
    last = pdf.iloc[-1]

    i = len(y) - 1
    feat = compute_features_at_entry(i, y, x, betas, errors, z_scores, ts)

    # Compare key features (rounded in both paths)
    keys = [
        "z_entry",
        "z_velocity",
        "spread_std",
        "beta_stability",
        "beta",
        "vol_ratio",
        "correlation_500",
        "trend_strength",
        "hour",
        "day_of_week",
        "ret_X_4h",
        "ret_Y_4h",
        "atr_ratio",
        "entry_atr",
        "vol_regime",
    ]

    # Rounded features can differ slightly due to pandas vs numpy rounding paths.
    tolerances = {
        "spread_std": 0.1,
        "entry_atr": 0.1,
        "ret_X_4h": 0.1,
        "ret_Y_4h": 0.1,
        "trend_strength": 0.02,
        "vol_ratio": 0.02,
        "correlation_500": 0.02,
        "beta_stability": 0.01,
        "atr_ratio": 0.02,
        "vol_regime": 0.02,
        "z_entry": 0.01,
        "z_velocity": 0.01,
        "beta": 0.01,
        "hour": 0.0,
        "day_of_week": 0.0,
    }

    for k in keys:
        tol = tolerances.get(k, 0.05)
        _assert_close(float(last[k]), float(feat[k]), tol=tol, label=k)

    print("[PASS] test_inference_feature_parity")


def test_kalman_centering_parity():
    y, x = _make_series()

    betas_train, errors_train = compute_kalman_states(y, x)

    inf = MetaModelInference(load_model=False)
    betas_inf, errors_inf = inf._compute_kalman(y, x)

    if not np.allclose(betas_train, betas_inf, atol=1e-9):
        raise AssertionError("Kalman betas diverge between training and inference centering.")
    if not np.allclose(errors_train, errors_inf, atol=1e-9):
        raise AssertionError("Kalman errors diverge between training and inference centering.")

    print("[PASS] test_kalman_centering_parity")


def main():
    test_no_future_leakage()
    test_kalman_centering_parity()
    test_inference_feature_parity()


if __name__ == "__main__":
    main()
