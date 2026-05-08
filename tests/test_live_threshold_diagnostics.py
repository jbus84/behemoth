from __future__ import annotations

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
    assert summary.loc[0, "replayed_threshold"] == pytest.approx(0.78)
