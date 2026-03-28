import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
import unittest.mock as mock
from types import SimpleNamespace
import numpy as np

from src.behemoth.api import server
from src.behemoth.api.server import app, _config
from src.behemoth.core.schemas import ModelFeatures

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_predict_blocks_on_rolling_threshold_gap_in_live_mode(client):
    # Setup mocks
    cand = mock.MagicMock()
    cand.bar_ticks = 100
    cand.horizon = 6
    cand.barrier_pips = 2.0
    cand.candidate_uid = "cand_100"
    cand.regime_desc = "all;barrier=2.0"

    feat = ModelFeatures(
        cost_est_pips=0.3, range_pips=6.0, ret1_pips=1.0, ret_z=0.4, ret_abs_z=0.4,
        vel_cost_units_h1=1.2, vel_abs_cost_units_h1=1.2, spread_z=0.2, tick_rate_z=0.1,
        hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
        bar_ticks=100.0, horizon=6.0, barrier_pips=2.0,
    )

    dummy_model = mock.MagicMock()
    dummy_model.predict_proba.return_value = np.array([[0.1, 0.95]]) # Strong signal

    # Governance config with rolling threshold requirement
    thr_cfg = {
        "threshold_source": "rolling_days",
        "rolling_threshold_days": 20,
        "rolling_threshold_min_history": 1000,
        "threshold_exec": 0.5,
    }

    orig_mode = _config.governance_mode
    _config.governance_mode = "live" # ENFORCE LIVE
    
    try:
        with (
            mock.patch.object(server, "_resolve_runtime_contract", return_value=SimpleNamespace(
                candidates=[cand], model_month="2025-01", cap_pips=1.2,
            )),
            mock.patch.object(server, "_ensure_model_and_threshold", return_value=(dummy_model, thr_cfg)),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=feat),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(server._state, "get_latest_close_ts", return_value=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)),
            # MOCK EMPTY HISTORY
            mock.patch.object(server._state, "get_rolling_threshold", return_value=None),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )
            assert r.status_code == 200
            rows = r.json()
            assert len(rows) == 1
            # VERIFY BLOCKED
            assert rows[0]["selected_exec"] == 0
            assert rows[0]["threshold_blocked"] is True
            assert rows[0]["threshold_block_reason"] == "ROLLING_HISTORY_GAP"
            assert rows[0]["threshold_exec"] == 2.0
    finally:
        _config.governance_mode = orig_mode

def test_predict_blocks_on_expired_schedule_in_live_mode(client):
    # Setup mocks
    cand = mock.MagicMock()
    cand.bar_ticks = 100
    cand.horizon = 6
    cand.barrier_pips = 2.0
    cand.candidate_uid = "cand_100"
    cand.regime_desc = "all;barrier=2.0"
    
    feat = ModelFeatures(
        cost_est_pips=0.3, range_pips=6.0, ret1_pips=1.0, ret_z=0.4, ret_abs_z=0.4,
        vel_cost_units_h1=1.2, vel_abs_cost_units_h1=1.2, spread_z=0.2, tick_rate_z=0.1,
        hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
        bar_ticks=100.0, horizon=6.0, barrier_pips=2.0,
    )

    dummy_model = mock.MagicMock()
    dummy_model.predict_proba.return_value = np.array([[0.1, 0.95]])

    # Expired schedule
    thr_cfg = {
        "threshold_source": "rolling_days",
        "threshold_schedule": {"2024-01-01": 0.5}, # OLD DATE
        "rolling_threshold_days": 0, # No rolling fallback
        "threshold_exec": 0.5,
    }

    orig_mode = _config.governance_mode
    _config.governance_mode = "live"
    
    try:
        with (
            mock.patch.object(server, "_resolve_runtime_contract", return_value=SimpleNamespace(
                candidates=[cand], model_month="2025-01", cap_pips=1.2,
            )),
            mock.patch.object(server, "_ensure_model_and_threshold", return_value=(dummy_model, thr_cfg)),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=feat),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(server._state, "get_latest_close_ts", return_value=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )
            assert r.status_code == 200
            rows = r.json()
            assert rows[0]["selected_exec"] == 0
            assert rows[0]["threshold_blocked"] is True
            assert rows[0]["threshold_block_reason"] == "NO_ROLLING_CONFIG"
    finally:
        _config.governance_mode = orig_mode

def test_predict_allows_static_fallback_in_research_mode(client):
    # Setup mocks
    cand = mock.MagicMock()
    cand.bar_ticks = 100
    cand.horizon = 6
    cand.barrier_pips = 2.0
    cand.candidate_uid = "cand_100"
    cand.regime_desc = "all;barrier=2.0"
    
    feat = ModelFeatures(
        cost_est_pips=0.3, range_pips=6.0, ret1_pips=1.0, ret_z=0.4, ret_abs_z=0.4,
        vel_cost_units_h1=1.2, vel_abs_cost_units_h1=1.2, spread_z=0.2, tick_rate_z=0.1,
        hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
        bar_ticks=100.0, horizon=6.0, barrier_pips=2.0,
    )

    dummy_model = mock.MagicMock()
    dummy_model.predict_proba.return_value = np.array([[0.1, 0.95]])

    # No rolling, no schedule
    thr_cfg = {
        "threshold_source": "static",
        "threshold_exec": 0.5,
    }

    orig_mode = _config.governance_mode
    _config.governance_mode = "research" # NOT LIVE
    
    try:
        with (
            mock.patch.object(server, "_resolve_runtime_contract", return_value=SimpleNamespace(
                candidates=[cand], model_month="2025-01", cap_pips=1.2,
            )),
            mock.patch.object(server, "_ensure_model_and_threshold", return_value=(dummy_model, thr_cfg)),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.object(server._state, "compute_features", return_value=feat),
            mock.patch.object(server._state, "compute_regime_quantiles", return_value={}),
            mock.patch.object(server._state, "get_latest_close_ts", return_value=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)),
        ):
            r = client.post(
                "/predict",
                json={
                    "symbol": "EURUSD",
                    "requested_volume_units": 10000,
                    "account_risk_enabled_override": False,
                },
            )
            assert r.status_code == 200
            rows = r.json()
            assert rows[0]["selected_exec"] == 1
            assert rows[0]["threshold_blocked"] is False
            assert rows[0]["threshold_exec"] == 0.5
    finally:
        _config.governance_mode = orig_mode
