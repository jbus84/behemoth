"""Placeholder predict path — no model wired in after the mining-pipeline removal.

TDD RED: documents the TARGET behavior that ``POST /predict`` returns
``{"predictions": [], "actions": []}`` when no model is wired in.

Today the live runtime still loads CatBoost models via governance locks and
the prediction orchestrator rejects an empty candidate set with HTTP 422
("No candidates registered for <SYMBOL>"). Phase 1 deleted the governance
lock directory, so to start the app at all we point ``BEHEMOTH_GOVERNANCE_DIR``
at an empty tmp directory — guaranteeing zero candidates load (i.e. "no model
wired in"). Tasks 2.2/2.3 replace the handler with a placeholder returning
empty predictions, which turns this test GREEN.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_predict_returns_empty_when_no_model(monkeypatch, tmp_path):
    from src.behemoth.api.server import app

    # AppConfig reads BEHEMOTH_SYMBOLS at import time; pin a minimal symbol set
    # so the lifespan initializes the symbol-specific state.
    monkeypatch.setenv("BEHEMOTH_SYMBOLS", "EURUSD")
    # Point the governance live-lock source at an EMPTY existing directory so
    # CandidateRegistry.load returns an empty (non-None) registry instead of
    # raising FileNotFoundError. This guarantees zero candidates are registered
    # ("no model wired in") while still letting the lifespan build the
    # PredictionOrchestrator (which requires a non-None live registry).
    empty_governance_dir = tmp_path / "governance_empty"
    empty_governance_dir.mkdir()
    monkeypatch.setenv("BEHEMOTH_GOVERNANCE_DIR", str(empty_governance_dir))

    # Enter the app as a context manager so the lifespan startup runs.
    with TestClient(app) as client:
        resp = client.post(
            "/predict",
            json={
                "symbol": "EURUSD",
                # PredictRequest's model_validator requires one of
                # risk_enabled_override / account_risk_enabled_override.
                "riskEnabledOverride": False,
                # The current handler's _resolve_requested_volume_units requires
                # one of requestedVolumeUnits / requestedLotSize; include it so
                # the request reaches the candidate-resolution step (and fails
                # there on the empty registry) rather than on input validation.
                "requestedVolumeUnits": 1.0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("predictions", []) == []
        assert body.get("actions", []) == []
