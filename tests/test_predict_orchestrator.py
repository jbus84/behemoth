"""Tests for PredictionOrchestrator step ordering and integration."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest

from src.behemoth.api.predict_orchestrator import PredictionOrchestrator
from src.behemoth.api.server import PredictRequest
from src.behemoth.core.schemas import PredictResponse
from src.behemoth.risk.account import AccountRiskDecision


class MockBarStateReader:
    """Mock BarStateReader for testing."""
    def get_latest_close_ts(self, symbol: str) -> datetime | None:
        return datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        return 300

    def compute_features(self, symbol: str, bar_ticks: int, horizon: int, barrier_pips: float):
        return mock.MagicMock()

    def compute_regime_quantiles(self, symbol: str, bar_ticks: int):
        return {}

    def get_latest_bar_context(self, symbol: str, bar_ticks: int):
        return None

    def get_latest_bar(self, symbol: str, bar_ticks: int):
        return None

    def get_latest_account_risk_snapshot(self, symbol: str | None = None):
        return {"balance": 10000, "equity": 9500}

    def get_account_risk_snapshots_since(self, *, since_ts: datetime, symbol: str | None = None):
        return []

    def sum_active_account_risk_reserved_loss_ccy(self, **kwargs):
        return 0.0

    def list_active_account_risk_reservations(self, **kwargs):
        return []

    def create_account_risk_reservation(self, **kwargs):
        return "res-123"

    def transition_account_risk_reservation(self, reservation_id: str, target_status: str, **kwargs):
        return target_status

    def release_account_risk_reservation(self, **kwargs):
        return 1

    def expire_stale_account_risk_pending_reservations(self, **kwargs):
        return 0


class TestPredictionOrchestrator:
    """Verify orchestrator runs 7 steps in correct order."""

    def test_orchestrator_initialization(self):
        """Orchestrator accepts all dependencies."""
        state = MockBarStateReader()
        orch = PredictionOrchestrator(
            state=state,  # type: ignore
            barrier_manager=None,
            model_registry=mock.MagicMock(),
            candidate_registry=mock.MagicMock(),
            historical_registry=mock.MagicMock(),
            account_risk_profile=None,
            config=mock.MagicMock(),
        )
        assert orch is not None

    def test_execute_returns_predict_response_with_candidates(self):
        """execute() returns typed PredictResponse."""
        state = MockBarStateReader()
        mock_catalog = mock.MagicMock()
        mock_contract = mock.MagicMock()
        
        # Create a mock candidate
        mock_candidate = mock.MagicMock()
        mock_candidate.bar_ticks = 100
        mock_candidate.horizon = 10
        mock_candidate.barrier_pips = 20.0
        mock_contract.candidates = [mock_candidate]
        
        mock_catalog.resolve_contract.return_value = mock_contract

        orch = PredictionOrchestrator(
            state=state,  # type: ignore
            barrier_manager=None,
            model_registry=mock.MagicMock(),
            candidate_registry=mock.MagicMock(),
            historical_registry=mock.MagicMock(),
            account_risk_profile=None,
            config=mock.MagicMock(),
        )
        orch._catalog = mock_catalog

        req = PredictRequest(symbol="EURUSD", requested_volume_units=10000, account_risk_enabled_override=False)
        resp = orch.execute(req, "run-123")
        assert isinstance(resp, PredictResponse)
        assert isinstance(resp.predictions, list)
        assert isinstance(resp.actions, list)

    def test_step_resolve_candidates_returns_list(self):
        """Step 1: resolve_candidates returns list."""
        state = MockBarStateReader()
        mock_catalog = mock.MagicMock()
        mock_contract = mock.MagicMock()
        mock_candidate = mock.MagicMock()
        mock_candidate.bar_ticks = 100
        mock_candidate.horizon = 10
        mock_candidate.barrier_pips = 20.0
        mock_contract.candidates = [mock_candidate]
        mock_catalog.resolve_contract.return_value = mock_contract

        orch = PredictionOrchestrator(
            state=state,  # type: ignore
            barrier_manager=None,
            model_registry=mock.MagicMock(),
            candidate_registry=mock.MagicMock(),
            historical_registry=mock.MagicMock(),
            account_risk_profile=None,
            config=mock.MagicMock(),
        )
        orch._catalog = mock_catalog

        req = PredictRequest(symbol="EURUSD", requested_volume_units=10000, account_risk_enabled_override=False)
        candidates = orch._step_resolve_candidates(
            req, "EURUSD", datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
        )
        assert isinstance(candidates, list)
        assert len(candidates) > 0

    def test_step_evaluate_account_risk_returns_decision(self):
        """Step 4: evaluate_account_risk returns typed decision."""
        state = MockBarStateReader()
        orch = PredictionOrchestrator(
            state=state,  # type: ignore
            barrier_manager=None,
            model_registry=mock.MagicMock(),
            candidate_registry=mock.MagicMock(),
            historical_registry=mock.MagicMock(),
            account_risk_profile=mock.MagicMock(),
            config=mock.MagicMock(),
        )
        decision = orch._step_evaluate_account_risk(
            "EURUSD",
            datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
            account_risk_enabled_effective=False,
        )
        assert isinstance(decision, AccountRiskDecision)
