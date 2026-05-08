from __future__ import annotations

import json

import duckdb
import pandas as pd
import pytest


def test_classifies_parity_breach_before_threshold_drift() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=False,
            feature_parity_checked=True,
            current_pool_lag_detected=True,
            live_distribution_unusual=True,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "PARITY_BREACH"


def test_classifies_parity_breach_when_threshold_replay_does_not_match() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=False,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=False,
            live_distribution_unusual=False,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "PARITY_BREACH"


def test_classifies_threshold_drift_when_parity_passes_and_pool_lags() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=True,
            live_distribution_unusual=True,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "THRESHOLD_DRIFT"


def test_classifies_model_validity_concern_when_earlier_gates_pass() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=False,
            live_distribution_unusual=True,
            model_validity_concern=True,
            evidence_missing=False,
        )
    )

    assert result == "MODEL_VALIDITY_CONCERN"


def test_classifies_runtime_variance_when_no_concern_is_detected() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=False,
            live_distribution_unusual=False,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "RUNTIME_VARIANCE"


def test_classifies_runtime_variance_when_live_distribution_is_unusual() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=True,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=True,
            current_pool_lag_detected=False,
            live_distribution_unusual=True,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "RUNTIME_VARIANCE"


@pytest.mark.parametrize(
    ("threshold_pool_complete", "feature_parity_checked"),
    [
        (False, True),
        (True, False),
    ],
)
def test_classifies_inconclusive_when_threshold_pool_or_parity_check_is_missing(
    threshold_pool_complete: bool,
    feature_parity_checked: bool,
) -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=threshold_pool_complete,
            threshold_replay_matches=True,
            feature_parity_passed=True,
            feature_parity_checked=feature_parity_checked,
            current_pool_lag_detected=False,
            live_distribution_unusual=False,
            model_validity_concern=False,
            evidence_missing=False,
        )
    )

    assert result == "INCONCLUSIVE"


def test_classifies_inconclusive_when_required_evidence_is_missing() -> None:
    from src.behemoth.diagnostics.live_threshold import DiagnosticInputs, classify_diagnostic

    result = classify_diagnostic(
        DiagnosticInputs(
            threshold_pool_complete=False,
            threshold_replay_matches=False,
            feature_parity_passed=False,
            feature_parity_checked=False,
            current_pool_lag_detected=False,
            live_distribution_unusual=False,
            model_validity_concern=False,
            evidence_missing=True,
        )
    )

    assert result == "INCONCLUSIVE"


def _audit_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
        """
    )
    rows = [
        (
            "2026-05-01T00:00:00Z",
            "2026-05-01T00:00:00Z",
            "EURUSD",
            "oco|EURUSD|100|h6|s1",
            0.70,
            0.60,
            "{}",
            "2026-04",
            "threshold_seed",
        ),
        (
            "2026-05-04T00:00:00Z",
            "2026-05-04T00:00:00Z",
            "EURUSD",
            "oco|EURUSD|100|h6|s1",
            0.80,
            0.60,
            "{}",
            "2026-04",
            "warmup",
        ),
        (
            "2026-05-08T00:00:00Z",
            "2026-05-08T00:00:00Z",
            "EURUSD",
            "oco|EURUSD|100|h6|s1",
            0.50,
            0.60,
            "{}",
            "2026-04",
            "jforex_live",
        ),
    ]
    con.executemany("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return con


def test_threshold_pool_audit_reconstructs_quantile_and_sources() -> None:
    from src.behemoth.diagnostics.live_threshold import audit_threshold_pool

    con = _audit_db()
    try:
        detail, summary = audit_threshold_pool(
            con,
            symbol="EURUSD",
            execution_quantile=0.9,
            lookback_days=20,
            min_history=1,
            as_of=pd.Timestamp("2026-05-09T00:00:00Z"),
            live_run_id="jforex_live",
        )
    finally:
        con.close()

    assert len(detail) == 3
    assert set(detail["source_period"]) == {"seed", "warmup", "live"}
    assert summary.loc[0, "pool_rows"] == 3
    assert summary.loc[0, "live_rows"] == 1
    assert summary.loc[0, "p90"] == pytest.approx(0.78)
    assert summary.loc[0, "replayed_threshold"] == pytest.approx(0.80)


def test_feature_parity_reports_mismatched_feature_value() -> None:
    from src.behemoth.diagnostics.live_threshold import compare_feature_parity

    live = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "features_json": json.dumps({"range_pips": 8.0, "cost_est_pips": 1.0}),
            }
        ]
    )
    recomputed = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "range_pips": 9.0,
                "cost_est_pips": 1.0,
            }
        ]
    )

    result = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips", "cost_est_pips"],
        tolerance=1e-9,
    )

    assert result.loc[0, "feature"] == "range_pips"
    assert result.loc[0, "status"] == "MISMATCH"
    assert result.loc[0, "abs_diff"] == pytest.approx(1.0)


def test_feature_parity_reports_missing_when_live_is_empty() -> None:
    from src.behemoth.diagnostics.live_threshold import compare_feature_parity

    recomputed = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|2",
                "range_pips": 9.0,
            }
        ]
    )

    result = compare_feature_parity(
        pd.DataFrame(columns=["close_ts", "candidate_uid", "features_json"]),
        recomputed,
        feature_columns=["range_pips"],
        tolerance=1e-9,
    )

    assert result.loc[0, "feature"] == "range_pips"
    assert result.loc[0, "status"] == "MISSING"
    assert pd.isna(result.loc[0, "live_value"])
    assert result.loc[0, "recomputed_value"] == pytest.approx(9.0)


def test_feature_parity_returns_expected_columns_when_all_values_pass() -> None:
    from src.behemoth.diagnostics.live_threshold import compare_feature_parity

    live = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|2",
                "features_json": json.dumps({"range_pips": 9.0}),
            }
        ]
    )
    recomputed = pd.DataFrame(
        [
            {
                "close_ts": pd.Timestamp("2026-05-08T00:00:00Z"),
                "candidate_uid": "oco|EURUSD|100|h6|2",
                "range_pips": 9.0,
            }
        ]
    )

    result = compare_feature_parity(
        live,
        recomputed,
        feature_columns=["range_pips"],
        tolerance=1e-9,
    )

    assert list(result.columns) == [
        "close_ts",
        "candidate_uid",
        "feature",
        "live_value",
        "recomputed_value",
        "abs_diff",
        "status",
    ]
    assert result.empty


def test_recompute_features_from_runtime_bars_uses_candidate_uid_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.behemoth.diagnostics import live_threshold as module

    bars = pd.DataFrame(
        {
            "ts": pd.date_range("2026-05-08T00:00:00Z", periods=2, freq="100s", tz="UTC"),
            "close_ts": pd.date_range(
                "2026-05-08T00:01:39Z", periods=2, freq="100s", tz="UTC"
            ),
            "open_bid": [1.0, 1.1],
            "high_bid": [1.2, 1.3],
            "low_bid": [0.9, 1.0],
            "close_bid": [1.15, 1.25],
            "spread": [0.0002, 0.0002],
            "tick_volume": [100, 100],
            "hl_first": [1.0, -1.0],
            "hl_pos_frac": [0.4, 0.6],
            "high_ask": [1.2002, 1.3002],
            "close_ask": [1.1502, 1.2502],
        }
    )

    def fake_compute(df: pd.DataFrame, **kwargs):
        assert kwargs["symbol"] == "EURUSD"
        assert kwargs["bar_ticks"] == 100
        assert kwargs["horizon"] == 6
        assert kwargs["barrier_pips"] == 2.0
        return pd.DataFrame({"range_pips": [8.0, 9.0], "cost_est_pips": [1.0, 1.1]})

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_compute)

    out = module.recompute_features_from_runtime_bars(
        bars,
        symbol="EURUSD",
        candidate_uid="oco|EURUSD|100|h6|2",
        feature_columns=["range_pips", "cost_est_pips"],
    )

    assert list(out["candidate_uid"].unique()) == ["oco|EURUSD|100|h6|2"]
    assert float(out.iloc[-1]["range_pips"]) == pytest.approx(9.0)


@pytest.mark.parametrize(
    "candidate_uid",
    [
        "library|EURUSD|100|h6|b2",
        "oco|EURUSD|100|h6|oco_first_touch_clean__high_abs_vel_q80__k2",
    ],
)
def test_recompute_features_from_runtime_bars_parses_encoded_barrier(
    monkeypatch: pytest.MonkeyPatch,
    candidate_uid: str,
) -> None:
    from src.behemoth.diagnostics import live_threshold as module

    bars = pd.DataFrame(
        {
            "ts": pd.date_range("2026-05-08T00:00:00Z", periods=1, freq="100s", tz="UTC"),
            "close_ts": pd.date_range(
                "2026-05-08T00:01:39Z", periods=1, freq="100s", tz="UTC"
            ),
        }
    )

    def fake_compute(df: pd.DataFrame, **kwargs):
        assert kwargs["symbol"] == "EURUSD"
        assert kwargs["bar_ticks"] == 100
        assert kwargs["horizon"] == 6
        assert kwargs["barrier_pips"] == 2.0
        return pd.DataFrame({"range_pips": [8.0]})

    monkeypatch.setattr(module, "compute_feature_matrix_from_bars", fake_compute)

    out = module.recompute_features_from_runtime_bars(
        bars,
        symbol="EURUSD",
        candidate_uid=candidate_uid,
        feature_columns=["range_pips"],
    )

    assert list(out["candidate_uid"].unique()) == [candidate_uid]
    assert float(out.iloc[0]["range_pips"]) == pytest.approx(8.0)
