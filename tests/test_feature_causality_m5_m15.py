from datetime import datetime, timedelta

import numpy as np

from behemoth.core.features import compute_features_at_entry
from behemoth.core.kalman import compute_kalman_states
from behemoth.core.zscore import compute_z_scores


def _make_series(n=900, seed=42):
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.normal(0, 0.01, n)) + 4.0
    y = 1.1 * x + rng.normal(0, 0.01, n)
    return y, x


def _make_timestamps(n=900):
    start = datetime(2020, 1, 1)
    return np.array([start + timedelta(minutes=i) for i in range(n)], dtype="datetime64[ns]")


def _assert_close(a, b, tol=1e-6, label="value"):
    if not np.isfinite(a) and not np.isfinite(b):
        return
    if abs(a - b) > tol:
        raise AssertionError(f"Mismatch for {label}: {a} vs {b} (tol={tol})")


def _check_causality(bar_minutes):
    y, x = _make_series()
    ts = _make_timestamps(len(y))

    betas, errors, ret_betas = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    i = 800
    feat_orig = compute_features_at_entry(
        i, y, x, betas, errors, ret_betas, z_scores, ts, bar_minutes=bar_minutes
    )

    # Modify future values only
    y2 = y.copy()
    x2 = x.copy()
    y2[i + 1:] += 0.5
    x2[i + 1:] -= 0.3

    betas2, errors2, ret_betas2 = compute_kalman_states(y2, x2)
    z_scores2 = compute_z_scores(errors2)

    # Causality checks
    assert np.allclose(betas[: i + 1], betas2[: i + 1], atol=1e-9)
    assert np.allclose(errors[: i + 1], errors2[: i + 1], atol=1e-9)
    assert np.allclose(z_scores[: i + 1], z_scores2[: i + 1], atol=1e-9)
    assert np.allclose(ret_betas[: i + 1], ret_betas2[: i + 1], atol=1e-9)

    feat_new = compute_features_at_entry(
        i, y2, x2, betas2, errors2, ret_betas2, z_scores2, ts, bar_minutes=bar_minutes
    )

    for k in feat_orig.keys():
        _assert_close(float(feat_orig[k]), float(feat_new[k]), tol=1e-6, label=k)


def test_feature_causality_m15():
    _check_causality(15)


def test_feature_causality_m5():
    _check_causality(5)
