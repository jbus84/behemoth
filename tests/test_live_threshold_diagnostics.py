from __future__ import annotations

import pandas as pd


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
