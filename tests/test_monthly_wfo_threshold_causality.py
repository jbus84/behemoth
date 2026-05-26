from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.run_tick_opportunity_monthly_wfo import (
    _attach_stable_event_ids,
    _rolling_day_threshold_vector,
)


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


def test_rolling_threshold_accumulates_test_day_predictions() -> None:
    """After day D's threshold is computed, day D's test predictions
    should influence day D+1's threshold."""
    train_ts = pd.Series(pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"], utc=True))
    train_p = np.array([0.3, 0.4], dtype=float)
    test_ts = pd.Series(
        pd.to_datetime(
            [
                "2025-01-03T00:00:00Z",
                "2025-01-04T00:00:00Z",
            ],
            utc=True,
        )
    )
    # Test day 1 has a very high prediction that should shift day 2's threshold
    test_p = np.array([0.95, 0.5], dtype=float)

    thr, src = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p,
        q=0.9,
        lookback_days=5,
        min_history=1,
    )

    # Day 1 threshold: 90th percentile of [0.3, 0.4] = 0.39
    # Day 2 threshold: 90th percentile of [0.3, 0.4, 0.95] = 0.785
    # Without accumulation, day 2 would also be 0.39
    day1_thr = float(np.quantile([0.3, 0.4], 0.9))
    day2_thr = float(np.quantile([0.3, 0.4, 0.95], 0.9))
    assert np.isclose(thr[0], day1_thr), f"Day 1: {thr[0]} != {day1_thr}"
    assert np.isclose(thr[1], day2_thr), f"Day 2: {thr[1]} != {day2_thr}"
    assert src[0] == "rolling_history"
    assert src[1] == "rolling_history"


def test_rolling_threshold_accumulation_preserves_causal_boundary() -> None:
    """Day D's own test predictions must NOT influence day D's threshold."""
    train_ts = pd.Series(pd.to_datetime(["2025-01-01T00:00:00Z"], utc=True))
    train_p = np.array([0.5], dtype=float)
    test_ts = pd.Series(pd.to_datetime(["2025-01-03T00:00:00Z"], utc=True))
    # Even with a wildly different test prediction, day 1's threshold
    # should only depend on training data
    test_p_low = np.array([0.01], dtype=float)
    test_p_high = np.array([0.99], dtype=float)

    thr_low, _ = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p_low,
        q=0.9,
        lookback_days=5,
        min_history=1,
    )
    thr_high, _ = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p_high,
        q=0.9,
        lookback_days=5,
        min_history=1,
    )

    assert np.isclose(thr_low[0], thr_high[0], equal_nan=True)


def test_attach_stable_event_ids_assigns_deterministic_keys() -> None:
    df = pd.DataFrame(
        [
            {"candidate_uid": "c1", "close_ts": "2025-07-01T00:00:03Z"},
            {"candidate_uid": "c1", "close_ts": "2025-07-01T00:00:01Z"},
            {"candidate_uid": "c2", "close_ts": "2025-07-02T00:00:01Z"},
        ]
    )
    out = _attach_stable_event_ids(df)
    c1 = out[out["candidate_uid"] == "c1"].sort_values("close_ts")
    assert c1["event_ordinal"].tolist() == [0, 1]
    assert c1["scored_row_id"].tolist() == ["2025-07|c1|0", "2025-07|c1|1"]


def test_family_model_artifact_stem_includes_family() -> None:
    from scripts.run_tick_opportunity_monthly_wfo import _model_artifact_stem

    assert _model_artifact_stem("EURUSD", "directional", "2026-02") == (
        "EURUSD_directional_model_2026-02"
    )


def test_export_train_predictions_parquet(tmp_path: Path) -> None:
    """Training predictions export should contain (day, pred_prob) rows
    matching the training data used by the rolling threshold."""
    from scripts.run_tick_opportunity_monthly_wfo import _export_train_predictions

    train_ts = pd.Series(
        pd.to_datetime(
            ["2025-01-01T10:00:00Z", "2025-01-01T11:00:00Z", "2025-01-02T10:00:00Z"],
            utc=True,
        )
    )
    train_p = np.array([0.3, 0.4, 0.7], dtype=float)
    out_path = tmp_path / "EURUSD_train_predictions_2025-02.parquet"

    _export_train_predictions(
        train_ts=train_ts,
        train_p=train_p,
        out_path=out_path,
    )

    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert list(df.columns) == ["day", "pred_prob"]
    assert len(df) == 3
    assert df["pred_prob"].tolist() == [0.3, 0.4, 0.7]
    # Days should be date objects, floored from timestamps
    assert str(df["day"].iloc[0]) == "2025-01-01"
    assert str(df["day"].iloc[2]) == "2025-01-02"
