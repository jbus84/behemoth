from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.run_tick_opportunity_monthly_wfo import _rolling_day_threshold_vector


def test_rolling_threshold_not_affected_by_future_test_days() -> None:
    train_ts = pd.Series(pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"], utc=True))
    train_p = np.array([0.1, 0.2], dtype=float)
    test_ts = pd.Series(
        pd.to_datetime(
            [
                "2025-01-03T00:00:00Z",
                "2025-01-04T00:00:00Z",
                "2025-01-05T00:00:00Z",
            ],
            utc=True,
        )
    )
    p_a = np.array([0.5, 0.51, 0.52], dtype=float)
    p_b = np.array([0.5, 0.99, 0.01], dtype=float)

    thr_a, src_a = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=p_a,
        q=0.5,
        lookback_days=2,
        min_history=1,
    )
    thr_b, src_b = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=p_b,
        q=0.5,
        lookback_days=2,
        min_history=1,
    )

    assert np.isclose(thr_a[0], thr_b[0], equal_nan=True)
    assert src_a[0] == src_b[0]


def test_rolling_threshold_insufficient_history_uses_train_fallback_only() -> None:
    train_ts = pd.Series(pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"], utc=True))
    train_p = np.array([0.2, 0.8], dtype=float)
    test_ts = pd.Series(pd.to_datetime(["2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"], utc=True))
    test_p = np.array([0.1, 0.9], dtype=float)

    thr, src = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p,
        q=0.5,
        lookback_days=1,
        min_history=1000,
    )

    expected = float(np.quantile(train_p, 0.5))
    assert np.allclose(thr, expected, equal_nan=True)
    assert set(src.tolist()) == {"train_fallback"}


def test_rolling_threshold_no_train_history_returns_nan_and_no_history_source() -> None:
    train_ts = pd.Series([], dtype="datetime64[ns, UTC]")
    train_p = np.array([], dtype=float)
    test_ts = pd.Series(pd.to_datetime(["2025-01-03T00:00:00Z", "2025-01-04T00:00:00Z"], utc=True))
    test_p = np.array([0.1, 0.9], dtype=float)

    thr, src = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p,
        q=0.9,
        lookback_days=20,
        min_history=1000,
    )

    assert np.isnan(thr).all()
    assert set(src.tolist()) == {"no_history"}
    selected = np.isfinite(thr) & (test_p >= thr)
    assert int(selected.sum()) == 0
