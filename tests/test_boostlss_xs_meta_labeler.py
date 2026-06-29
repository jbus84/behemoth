"""Tests for MetaLabeler."""
from __future__ import annotations

import numpy as np


def _make_synthetic_flags(n: int = 400, n_horizons: int = 5) -> dict:
    rng = np.random.default_rng(7)
    train_n = n // 2
    flags_by_horizon: dict[int, dict[str, np.ndarray]] = {}
    y_by_horizon: dict[int, np.ndarray] = {}

    for h in range(1, n_horizons + 1):
        mu = np.concatenate([np.full(train_n, np.nan), rng.normal(0, 1.5, n - train_n)])
        sigma = np.concatenate([np.full(train_n, np.nan), rng.uniform(0.5, 2.0, n - train_n)])
        nu = np.concatenate([np.full(train_n, np.nan), rng.uniform(2, 15, n - train_n)])
        direction = np.concatenate([np.full(train_n, np.nan), np.sign(mu[train_n:])])
        flags_by_horizon[h] = {
            "mu_flag": np.concatenate([np.full(train_n, np.nan),
                                       (np.abs(mu[train_n:]) > 1.5).astype(float)]),
            "mu_mag": np.abs(mu),
            "sigma_flag": np.concatenate([np.full(train_n, np.nan),
                                          (sigma[train_n:] < 1.0).astype(float)]),
            "sigma_mag": sigma,
            "nu_flag": np.concatenate([np.full(train_n, np.nan),
                                       (nu[train_n:] < 5).astype(float)]),
            "nu_mag": nu,
            "direction": direction,
        }
        y_by_horizon[h] = rng.normal(0, 2, n)

    symbols = ["EURUSD"] * (n // 2) + ["GBPUSD"] * (n // 2)
    close_ts = np.arange(n).astype("datetime64[s]")
    return {
        "flags_by_horizon": flags_by_horizon,
        "y_by_horizon": y_by_horizon,
        "direction": flags_by_horizon[1]["direction"],
        "symbols_arr": symbols,
        "close_ts_arr": close_ts,
    }


def test_meta_labeler_returns_probability_array():
    from scripts.boostlss_xs.meta_labeler import MetaLabeler

    data = _make_synthetic_flags()
    ml = MetaLabeler()
    probs = ml.fit_predict(**data)
    assert probs.shape == (400,)
    oos = probs[~np.isnan(probs)]
    assert (oos >= 0).all() and (oos <= 1).all()


def test_meta_labeler_nan_for_train_rows():
    from scripts.boostlss_xs.meta_labeler import MetaLabeler

    data = _make_synthetic_flags(n=400)
    ml = MetaLabeler()
    probs = ml.fit_predict(**data)
    # First half should be NaN (train rows)
    assert np.isnan(probs[:200]).all()


def test_label_construction_direction_aware():
    """Label is 1 only when return aligns with predicted direction."""
    from scripts.boostlss_xs.meta_labeler import _build_label

    direction = np.array([1.0, -1.0, 1.0, -1.0])
    y = np.array([2.0, -2.0, -2.0, 2.0])  # first two align, last two don't
    threshold = 1.0
    labels = _build_label(direction, y, threshold)
    np.testing.assert_array_equal(labels, [1, 1, 0, 0])
