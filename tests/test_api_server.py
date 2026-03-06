#!/usr/bin/env python3
"""TDD tests for the FastAPI inference server.

Uses httpx + FastAPI TestClient to validate endpoints
without needing CatBoost models (mocked where necessary).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.behemoth.api.server import app


@pytest.fixture
def client():
    """Create a test client with a fresh state manager."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "no_models")
        assert "utc_now" in body
        assert "bar_counts" in body

    def test_health_contains_all_symbols(self, client):
        r = client.get("/health")
        body = r.json()
        for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
            assert sym in body["bar_counts"]

    def test_health_uninitialized_state(self, client):
        """If the state manager is missing, health should return 503."""
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            r = client.get("/health")
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "behemoth_" in r.text


class TestFtmoRiskEndpoints:
    def test_ftmo_limits_endpoint(self, client):
        r = client.get("/risk/ftmo/limits")
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body
        if body["enabled"]:
            assert body["profile_id"] is not None
            assert body["daily_loss_limit_hard"] is not None
            assert body["max_loss_limit_hard"] is not None

    def test_ftmo_snapshot_and_status(self, client):
        r = client.post(
            "/risk/ftmo/snapshot",
            json={
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 9950.0,
                "snapshot_ts": "2025-01-01T10:00:00Z",
            },
        )
        assert r.status_code == 201
        status = client.get("/risk/ftmo/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "allow_trading" in body
        assert body["snapshot_available"] in (True, False)

    def test_ftmo_reservations_status_and_release(self, client):
        status = client.get("/risk/ftmo/reservations/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "active_count" in body
        release = client.post(
            "/risk/ftmo/reservations/release",
            json={"candidate_uid": "missing_candidate_uid"},
        )
        assert release.status_code == 200
        assert "released_count" in release.json()


class TestStatusEndpoint:
    def test_status_returns_list(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 6
        symbols = {s["symbol"] for s in body}
        assert symbols == {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}


class TestBarsEndpoint:
    def test_ingest_bar(self, client):
        bar = {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": "2025-12-01T10:00:00Z",
            "close_ts": "2025-12-01T10:00:30Z",
            "open": 1.10500,
            "high": 1.10600,
            "low": 1.10400,
            "close": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
        }
        r = client.post("/bars", json=bar)
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert body["symbol"] == "EURUSD"
        assert body["bar_count"] >= 1

    def test_ingest_bar_validation_error(self, client):
        bar = {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": "2025-12-01T10:00:00Z",
            "close_ts": "2025-12-01T10:00:30Z",
            "open": -1.0,  # invalid
            "high": 1.10600,
            "low": 1.10400,
            "close": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
        }
        r = client.post("/bars", json=bar)
        assert r.status_code == 422

    def test_ingest_bar_uninitialized_state(self, client):
        """If _state is None, ingest_bar returns 503."""
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            bar = {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "timestamp": "2025-12-01T10:00:00Z",
                "close_ts": "2025-12-01T10:00:30Z",
                "open": 1.10500,
                "high": 1.10600,
                "low": 1.10400,
                "close": 1.10550,
                "spread": 0.00012,
                "tick_volume": 100,
            }
            r = client.post("/bars", json=bar)
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state



class TestPredictEndpoint:
    def test_predict_requires_size(self, client):
        r = client.post("/predict", json={"symbol": "EURUSD"})
        assert r.status_code == 422

    def test_predict_insufficient_warmup(self, client):
        """With no bars ingested, predict should return 422."""
        r = client.post("/predict", json={
            "symbol": "EURUSD",
            "requested_volume_units": 10000,
        })
        assert r.status_code in (200, 422, 503)
        if r.status_code == 200:
            assert isinstance(r.json(), list)
        else:
            detail = r.json()["detail"].lower()
            assert "warmup" in detail or "candidate" in detail or "registry" in detail or "model" in detail

    def test_predict_uninitialized_state(self, client):
        """If _state is None, predict returns 503."""
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state

    def test_predict_unloaded_registry(self, client):
        """If _registry is None, predict returns 503."""
        from src.behemoth.api import server
        original_registry = server._registry
        server._registry = None
        try:
            r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
            assert r.status_code == 503
            assert "Candidate registry not loaded" in r.json()["detail"]
        finally:
            server._registry = original_registry

    def test_predict_no_candidates(self, client):
        """If registry returns empty candidates, predict returns 422."""
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._registry, 'get_candidates', return_value=[]):
            r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
            assert r.status_code == 422
            assert "No candidates registered" in r.json()["detail"]

    def test_predict_no_model(self, client):
        """If CatBoost model isn't loaded, predict returns 503."""
        import unittest.mock as mock

        from src.behemoth.api import server

        # We dummy out the warmup check and feature computation so we hit the model check
        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 12
        dummy_cand.barrier_pips = 10.0

        with (
            mock.patch.object(server._registry, 'get_candidates', return_value=[dummy_cand]),
            mock.patch.object(server, '_check_warmup', return_value=None),
        ):
            original_models = server._models
            server._models = {}  # Empty models
            try:
                r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
                assert r.status_code == 503
                assert "No CatBoost model loaded" in r.json()["detail"]
            finally:
                server._models = original_models

    def test_predict_feature_computation_fails(self, client):
        """If _state.compute_features returns None, predict returns 422."""
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 12
        dummy_cand.barrier_pips = 10.0

        with (
            mock.patch.object(server._registry, 'get_candidates', return_value=[dummy_cand]),
            mock.patch.object(server, '_check_warmup', return_value=None),
            mock.patch.dict(server._models, {"EURUSD": mock.MagicMock()}),
            mock.patch.object(server._state, 'compute_features', return_value=None),
        ):
            r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
            assert r.status_code == 422
            assert "Feature computation failed" in r.json()["detail"]

    def test_predict_success(self, client):
        """Mock the pipeline to simulate a successful prediction return."""
        import unittest.mock as mock
        from datetime import datetime, timezone

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 24
        dummy_cand.barrier_pips = 15.0
        dummy_cand.candidate_uid = "cand1"

        dummy_features = ModelFeatures(
            cost_est_pips=1.0, range_pips=10.0, ret1_pips=2.0, ret_z=0.5, ret_abs_z=0.5,
            vel_cost_units_h1=2.0, vel_abs_cost_units_h1=2.0, spread_z=0.1, tick_rate_z=0.1,
            hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0, horizon=24.0, barrier_pips=15.0
        )

        dummy_model = mock.MagicMock()
        import numpy as np
        dummy_model.predict_proba.return_value = np.array([[0.1, 0.85]])  # 85% probability

        with (
            mock.patch.object(server._registry, 'get_candidates', return_value=[dummy_cand]),
            mock.patch.object(server, '_check_warmup', return_value=None),
            mock.patch.dict(server._models, {"EURUSD": dummy_model}),
            mock.patch.object(server._state, 'compute_features', return_value=dummy_features),
            mock.patch.object(server._state, 'get_latest_close_ts', return_value=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ):
            snap = client.post(
                "/risk/ftmo/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post("/predict", json={"symbol": "EURUSD", "requested_volume_units": 10000})
            assert r.status_code == 200
            results = r.json()
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["pred_prob"] == 0.85
            assert results[0]["selected_exec"] == 1
            assert "risk_blocked" in results[0]

    def test_predict_allocator_blocks_when_budget_exceeded(self, client):
        import unittest.mock as mock
        from datetime import datetime, timezone

        import numpy as np

        from src.behemoth.api import server
        from src.behemoth.core.schemas import ModelFeatures

        cand_small = mock.MagicMock()
        cand_small.bar_ticks = 100
        cand_small.horizon = 6
        cand_small.barrier_pips = 3.0
        cand_small.candidate_uid = "cand_small"

        cand_large = mock.MagicMock()
        cand_large.bar_ticks = 100
        cand_large.horizon = 6
        cand_large.barrier_pips = 200.0
        cand_large.candidate_uid = "cand_large"

        dummy_features = ModelFeatures(
            cost_est_pips=0.1, range_pips=10.0, ret1_pips=2.0, ret_z=0.5, ret_abs_z=0.5,
            vel_cost_units_h1=2.0, vel_abs_cost_units_h1=2.0, spread_z=0.1, tick_rate_z=0.1,
            hour_utc=10.0, hl_first=1.0, hl_first_mean_24=0.5, hl_pos_frac_mean_24=0.5,
            bar_ticks=100.0, horizon=6.0, barrier_pips=3.0
        )
        dummy_model = mock.MagicMock()
        dummy_model.predict_proba.side_effect = [
            np.array([[0.1, 0.90]]),
            np.array([[0.1, 0.85]]),
        ]

        with (
            mock.patch.object(server._registry, "get_candidates", return_value=[cand_small, cand_large]),
            mock.patch.object(server, "_check_warmup", return_value=None),
            mock.patch.dict(server._models, {"EURUSD": dummy_model}),
            mock.patch.object(server._state, "compute_features", return_value=dummy_features),
            mock.patch.object(server._state, "get_latest_close_ts", return_value=datetime(2025, 1, 1, tzinfo=timezone.utc)),
            mock.patch.object(
                server,
                "_resolve_ftmo_account_eval",
                return_value={
                    "enabled": True,
                    "profile_id": "ftmo_10k_challenge_2step",
                    "allow_trading": True,
                    "block_reason": None,
                    "snapshot_available": True,
                    "daily_loss_headroom": 200.0,
                    "max_loss_headroom": 200.0,
                    "daily_loss_used": 0.0,
                    "max_loss_used": 0.0,
                    "trading_day_id": "2025-01-01",
                },
            ),
        ):
            snap = client.post(
                "/risk/ftmo/snapshot",
                json={
                    "symbol": "EURUSD",
                    "balance": 10000.0,
                    "equity": 10000.0,
                    "snapshot_ts": "2025-01-01T00:00:00Z",
                },
            )
            assert snap.status_code == 201
            r = client.post(
                "/predict",
                json={"symbol": "EURUSD", "requested_volume_units": 10000},
            )
            assert r.status_code == 200
            rows = r.json()
            assert len(rows) == 2
            blocked = [x for x in rows if x["risk_block_reason"] == "FTMO_RESERVED_BUDGET_EXCEEDED"]
            admitted = [x for x in rows if x["selected_exec"] == 1]
            assert len(blocked) == 1
            assert len(admitted) == 1
            assert admitted[0]["risk_reserved"] is True
            assert admitted[0]["risk_reservation_id"] is not None


class TestReloadEndpoint:
    def test_reload_returns_ok(self, client):
        r = client.post("/reload")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True


class TestTradeEndpoints:
    def test_open_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, 'open_trade', return_value=123):
            r = client.post("/trades/open", json={
                "symbol": "EURUSD",
                "candidate_uid": "test_cand",
                "broker_pos_id": "456",
                "side": "BUY",
                "entry_price": 1.1000,
                "entry_ts": "2025-01-01T00:00:00Z",
                "horizon": 12,
            })
            assert r.status_code == 200
            assert r.json()["internal_trade_id"] == 123

    def test_touch_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        mock_con = mock.MagicMock()
        mock_con.execute().fetchone.return_value = [999]

        with (
            mock.patch.object(server._state, '_con', mock_con),
            mock.patch.object(server._state, 'touch_trade'),
        ):
            r = client.post("/trades/touch", json={
                "symbol": "EURUSD",
                "broker_pos_id": "456",
            })
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_update_trade_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, 'update_trade'):
            r = client.post("/trades/update", json={
                "symbol": "EURUSD",
                "broker_pos_id": "456",
                "status": "CLOSED",
                "exit_price": 1.1050,
                "exit_ts": "2025-01-01T02:00:00Z",
                "pnl_pips": 50.0,
            })
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_get_active_trades_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        with mock.patch.object(server._state, 'get_active_trades', return_value=[]):
            r = client.get("/trades/active?symbol=EURUSD")
            assert r.status_code == 200
            assert r.json() == []

    def test_trade_endpoints_uninitialized_state(self, client):
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            assert client.post("/trades/open", json={"symbol": "E", "candidate_uid": "C", "broker_pos_id": "1", "side": "BUY", "entry_price": 1.0, "entry_ts": "2025-01-01T00:00:00Z", "horizon": 12}).status_code == 503
            assert client.post("/trades/touch", json={"symbol": "E", "broker_pos_id": "1"}).status_code == 503
            assert client.post("/trades/update", json={"symbol": "E", "broker_pos_id": "1", "status": "CLOSED"}).status_code == 503
            assert client.get("/trades/active?symbol=E").status_code == 503
        finally:
            server._state = original_state


class TestIngestionEndpoints:
    def test_backfill_uninitialized(self, client):
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            r = client.post("/backfill", json={"symbol": "EURUSD", "ticks": []})
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_ingest_tick_uninitialized(self, client):
        from src.behemoth.api import server
        original_state = server._state
        server._state = None
        try:
            r = client.post("/ticks", json={
                "symbol": "EURUSD", "timestamp": "2025-01-01T00:00:00Z",
                "bid": 1.1, "ask": 1.1
            })
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_backfill_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = ["bar1", "bar2"]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, 'append_bar') as mock_append,
            mock.patch.object(server._state, 'bar_count', return_value=300),
        ):
            r = client.post("/backfill", json={
                "symbol": "EURUSD",
                "ticks": [
                    {"symbol": "EURUSD", "timestamp": "2025-01-01T00:00:00Z", "bid": 1.1, "ask": 1.1},
                ]
            })
            assert r.status_code == 201
            res = r.json()
            assert res["bars_created"] == 2
            assert mock_append.call_count == 2
            assert res["warm"] is True

    def test_ingest_tick_success(self, client):
        import unittest.mock as mock

        from src.behemoth.api import server
        from src.behemoth.runtime.tick_aggregator import IncomingTickBar

        dummy_agg = mock.MagicMock()
        dummy_bar = IncomingTickBar(symbol="EURUSD", bar_ticks=100, timestamp="2025-01-01T00:00:00Z", close_ts="2025-01-01T00:00:10Z", open=1.0, high=1.0, low=1.0, close=1.0, spread=0.0, tick_volume=100.0, hl_first=1.0, hl_pos_frac=0.5)
        dummy_agg.add_ticks.return_value = [dummy_bar]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, 'append_bar') as mock_append,
            mock.patch.object(server._state, 'bar_count', return_value=150),
        ):
            r = client.post("/ticks", json={
                "symbol": "EURUSD", "timestamp": "2025-01-01T00:00:10Z", "bid": 1.1, "ask": 1.1
            })
            assert r.status_code == 201
            res = r.json()
            assert res["bar_completed"] is True
            assert res["completed_bar_ticks"] == [100]
            assert mock_append.call_count == 1
