#!/usr/bin/env python3
"""Kept-behavior route tests for the FastAPI inference server.

These tests cover the LIVE keep-set endpoints that survived the placeholder
refactor (commit 7d030d1c): ``/health``, ``/metrics``, ``/risk/account*``,
``/ticks``, ``/backfill``, ``/bars``, ``/trades/*``, ``/checkpoint``,
``/runtime/feed/status``, ``/status``, and ``/dashboard/``.

Removed-behavior tests (governance/model/historical-prediction system) were
intentionally dropped — they tested endpoints and code paths deleted by the
placeholder refactor. This file is a clean extraction from the original
``tests/test_api_server.py`` (commit 352075b7) with the governance-patching
fixture stripped and only the keep-set route classes retained.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.behemoth.api import server
from src.behemoth.api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with an isolated runtime DB per test.

    In placeholder mode ``_orchestrator`` is ``None`` after lifespan startup,
    so no governance-patching monkeypatch is required (the old
    ``_resolve_runtime_contract_for_family`` patch was the only blocker and
    has been removed along with the function it patched, which no longer
    exists on ``server``).
    """
    empty_gov = tmp_path / "governance_empty"
    empty_gov.mkdir()
    monkeypatch.setenv("BEHEMOTH_GOVERNANCE_DIR", str(empty_gov))
    original_persist_db_path = server._config.persist_db_path
    server._config.persist_db_path = str(tmp_path / "behemoth_runtime.duckdb")
    try:
        with TestClient(app) as c:
            yield c
    finally:
        server._config.persist_db_path = original_persist_db_path


# ── /health ───────────────────────────────────────────────────────────


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

    def test_health_reports_active_bar_ticks_and_governance_dir(self, client, monkeypatch):
        # In placeholder mode the health endpoint hardcodes governance_dir=""
        # and derives bar_ticks from _aggregators (always [100] from lifespan).
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {"bar_count": staticmethod(lambda sym, bt: 7 if bt == 100 else 0)},
            )(),
        )

        r = client.get("/health")

        assert r.status_code == 200
        body = r.json()
        assert body["governance_dir"] == ""
        assert body["bar_ticks"]["EURUSD"] == [100]
        assert body["bar_counts"]["EURUSD"] == 7

    def test_health_uninitialized_state(self, client):
        """If the state manager is missing, health should return 503."""
        original_state = server._state
        server._state = None
        try:
            r = client.get("/health")
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state

    def test_health_returns_503_before_lifespan_ready(self, client):
        """Health must return 503 while lifespan initialization is in progress."""
        original = server._lifespan_ready
        server._lifespan_ready = False
        try:
            r = client.get("/health")
            assert r.status_code == 503
            assert "Lifespan initialization in progress" in r.json()["detail"]
        finally:
            server._lifespan_ready = original


# ── /metrics ──────────────────────────────────────────────────────────


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "behemoth_" in r.text

    def test_metrics_drop_stale_equity_symbols_when_current_ledger_is_empty(self, client):
        server.METRIC_EQUITY_PIPS.clear()

        server._sync_equity_pips_metrics([{"symbol": "GBPUSD", "total_pnl": -17.9}])
        populated = client.get("/metrics")
        assert 'behemoth_equity_pips{symbol="GBPUSD"} -17.9' in populated.text

        server._sync_equity_pips_metrics([])
        cleared = client.get("/metrics")
        assert 'behemoth_equity_pips{symbol="GBPUSD"}' not in cleared.text

    def test_metrics_publish_broker_open_positions_separately_from_reservations(self, client):
        import unittest.mock as mock

        now = datetime(2026, 4, 10, 11, 30, 0, tzinfo=timezone.utc)
        created = now - timedelta(minutes=5)
        reservations = [
            {
                "reservation_id": "eur-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "EURUSD",
                "candidate_uid": "cand-1",
                "broker_pos_id": "bp-eur-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "eur-pending",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "EURUSD",
                "candidate_uid": "cand-2",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "gbp-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "GBPUSD",
                "candidate_uid": "cand-3",
                "broker_pos_id": "bp-gbp-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "SELL",
                "source": "algo",
            },
            {
                "reservation_id": "usdcad-open",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "USDCAD",
                "candidate_uid": "cand-4",
                "broker_pos_id": "bp-cad-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "aud-pending",
                "created_ts": created,
                "updated_ts": created,
                "symbol": "AUDUSD",
                "candidate_uid": "cand-5",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
        ]

        active_trades = {
            "EURUSD": [
                {
                    "broker_pos_id": "bp-eur-1",
                    "entry_bar_id": 10,
                    "horizon": 6,
                    "touch_bar_id": None,
                }
            ],
            "GBPUSD": [
                {
                    "broker_pos_id": "bp-gbp-1",
                    "entry_bar_id": 10,
                    "horizon": 6,
                    "touch_bar_id": None,
                }
            ],
            "USDCAD": [
                {
                    "broker_pos_id": "bp-cad-1",
                    "entry_bar_id": 10,
                    "horizon": 6,
                    "touch_bar_id": None,
                }
            ],
            "AUDUSD": [],
            "USDCHF": [],
            "USDJPY": [],
        }

        with (
            mock.patch.object(
                server._state, "list_active_account_risk_reservations", return_value=reservations
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(
                server._state,
                "get_all_symbols",
                return_value=["EURUSD", "GBPUSD", "USDCAD", "AUDUSD", "USDCHF", "USDJPY"],
            ),
            mock.patch.object(
                server._state, "get_active_trades", side_effect=lambda symbol: active_trades[symbol]
            ),
        ):
            summary = server._build_open_positions_summary(server._state, now)

        assert summary["total_open"] == 5
        assert summary["broker_confirmed"] == 3
        assert summary["pending_broker_confirm"] == 2

        metrics = client.get("/metrics")
        assert 'behemoth_open_positions_total{symbol="EURUSD"} 2.0' in metrics.text
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="EURUSD"} 1.0' in metrics.text
        )
        assert 'behemoth_broker_open_positions_total{symbol="EURUSD"} 1.0' in metrics.text
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="GBPUSD"} 0.0' in metrics.text
        )
        assert 'behemoth_broker_open_positions_total{symbol="GBPUSD"} 1.0' in metrics.text
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="USDCAD"} 0.0' in metrics.text
        )
        assert 'behemoth_broker_open_positions_total{symbol="USDCAD"} 1.0' in metrics.text
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="AUDUSD"} 1.0' in metrics.text
        )
        assert 'behemoth_broker_open_positions_total{symbol="AUDUSD"} 0.0' in metrics.text
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="USDCHF"} 0.0' in metrics.text
        )
        assert (
            'behemoth_pending_broker_confirm_positions_total{symbol="USDJPY"} 0.0' in metrics.text
        )

    def test_open_position_age_seconds_uses_oldest_broker_confirmed_trade(self, client):
        import unittest.mock as mock

        now = datetime(2026, 4, 10, 11, 30, 0, tzinfo=timezone.utc)
        older_pending = now - timedelta(minutes=20)
        newer_confirmed = now - timedelta(minutes=5)
        reservations = [
            {
                "reservation_id": "eur-pending",
                "created_ts": older_pending,
                "updated_ts": older_pending,
                "symbol": "EURUSD",
                "candidate_uid": "cand-1",
                "broker_pos_id": None,
                "status": "PENDING",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
            {
                "reservation_id": "eur-open",
                "created_ts": newer_confirmed,
                "updated_ts": newer_confirmed,
                "symbol": "EURUSD",
                "candidate_uid": "cand-2",
                "broker_pos_id": "bp-eur-1",
                "status": "OPEN",
                "reserved_loss_ccy": 10.0,
                "barrier_pips": 20.0,
                "cap_pips": 30.0,
                "cost_est_pips": 5.0,
                "volume_units": 1000.0,
                "side": "BUY",
                "source": "algo",
            },
        ]

        active_trades = {
            "EURUSD": [
                {
                    "broker_pos_id": "bp-eur-1",
                    "entry_bar_id": 10,
                    "horizon": 6,
                    "touch_bar_id": None,
                }
            ],
            "GBPUSD": [],
            "USDCAD": [],
            "AUDUSD": [],
            "USDCHF": [],
            "USDJPY": [],
        }

        with (
            mock.patch.object(
                server._state, "list_active_account_risk_reservations", return_value=reservations
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(
                server._state,
                "get_all_symbols",
                return_value=["EURUSD", "GBPUSD", "USDCAD", "AUDUSD", "USDCHF", "USDJPY"],
            ),
            mock.patch.object(
                server._state, "get_active_trades", side_effect=lambda symbol: active_trades[symbol]
            ),
        ):
            server._build_open_positions_summary(server._state, now)

        metrics = client.get("/metrics")
        assert 'behemoth_open_position_age_seconds{symbol="EURUSD"} 300.0' in metrics.text


# ── /risk/account* ────────────────────────────────────────────────────


class TestAccountRiskEndpoints:
    def test_account_limits_endpoint(self, client):
        r = client.get("/risk/account/limits")
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body

    def test_account_snapshot_and_status(self, client):
        r = client.post(
            "/risk/account/snapshot",
            json={
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 9950.0,
                "snapshot_ts": "2025-01-01T10:00:00Z",
            },
        )
        assert r.status_code == 201
        status = client.get("/risk/account/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "allow_trading" in body
        assert body["snapshot_available"] in (True, False)

    def test_account_reservations_status_and_release(self, client):
        status = client.get("/risk/account/reservations/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "active_count" in body
        release = client.post(
            "/risk/account/reservations/release",
            json={"candidate_uid": "missing_candidate_uid"},
        )
        assert release.status_code == 200
        assert "released_count" in release.json()

    def test_account_risk_limits_endpoint(self, client):
        r = client.get("/risk/account_risk/limits")
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body
        if body["enabled"]:
            assert body["profile_id"] is not None
            assert body["daily_loss_limit_hard"] is not None
            assert body["max_loss_limit_hard"] is not None

    def test_account_risk_snapshot_and_status(self, client):
        r = client.post(
            "/risk/account_risk/snapshot",
            json={
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 9950.0,
                "snapshot_ts": "2025-01-01T10:00:00Z",
            },
        )
        assert r.status_code == 201
        status = client.get("/risk/account_risk/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "allow_trading" in body
        assert body["snapshot_available"] in (True, False)

    def test_account_risk_reservations_status_and_release(self, client):
        status = client.get("/risk/account_risk/reservations/status?symbol=EURUSD")
        assert status.status_code == 200
        body = status.json()
        assert "active_count" in body
        release = client.post(
            "/risk/account_risk/reservations/release",
            json={"candidate_uid": "missing_candidate_uid"},
        )
        assert release.status_code == 200
        assert "released_count" in release.json()


# ── /status ───────────────────────────────────────────────────────────


class TestStatusEndpoint:
    def test_status_returns_list(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 6
        symbols = {s["symbol"] for s in body}
        assert symbols == {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}

    def test_status_surfaces_restart_reconciliation_failure(self, client, monkeypatch):
        # Placeholder /status no longer reads governance/model helpers; it only
        # surfaces restart_verdict/restart_reasons from the reconciliation
        # report and hardcodes the placeholder deployment_state fields.
        monkeypatch.setattr(
            server,
            "_config",
            type("Cfg", (), {"symbols": ["EURUSD", "GBPUSD"], "governance_mode": "live"})(),
        )
        monkeypatch.setattr(
            server,
            "_state",
            type(
                "StateStub",
                (),
                {"bar_count": staticmethod(lambda sym, bt: 11)},
            )(),
        )
        monkeypatch.setattr(
            server,
            "_load_restart_reconciliation_report",
            lambda: {
                "verdict": "incompatible",
                "reasons": [
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            },
        )

        r = client.get("/status")

        assert r.status_code == 200
        body = r.json()
        eurusd = next(row for row in body if row["symbol"] == "EURUSD")
        assert eurusd["restart_verdict"] == "incompatible"
        assert eurusd["restart_reasons"] == [
            "broker-linked symbols do not match broker snapshot symbols",
            "broker-linked position ids do not match broker snapshot order ids",
        ]
        assert eurusd["deployment_state"] == "placeholder"
        assert eurusd["model_loaded"] is False
        assert eurusd["families"] == []

    def test_runtime_feed_status_returns_symbols(self, client):
        r = client.get("/runtime/feed/status")
        assert r.status_code == 200
        body = r.json()
        assert "as_of_utc" in body
        assert "symbols" in body
        listed = {row["symbol"] for row in body["symbols"]}
        assert {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}.issubset(listed)


# ── /dashboard/ ───────────────────────────────────────────────────────


class TestDashboard:
    def test_dashboard_includes_deployment_state_label(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 200
        html = r.text
        assert "deployment_state" in html
        assert "NO_GO / Not Promoted" in html


# ── /bars ─────────────────────────────────────────────────────────────


class TestBarsEndpoint:
    def test_ingest_bar(self, client):
        bar = {
            "symbol": "EURUSD",
            "bar_ticks": 100,
            "timestamp": "2025-12-01T10:00:00Z",
            "close_ts": "2025-12-01T10:00:30Z",
            "open_bid": 1.10500,
            "high_bid": 1.10600,
            "low_bid": 1.10400,
            "close_bid": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
            "high_ask": 1.10612,
            "close_ask": 1.10562,
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
            "open_bid": -1.0,  # invalid
            "high_bid": 1.10600,
            "low_bid": 1.10400,
            "close_bid": 1.10550,
            "spread": 0.00012,
            "tick_volume": 100,
            "high_ask": 1.10612,
            "close_ask": 1.10562,
        }
        r = client.post("/bars", json=bar)
        assert r.status_code == 422

    def test_ingest_bar_uninitialized_state(self, client):
        """If _state is None, ingest_bar returns 503."""
        original_state = server._state
        server._state = None
        try:
            bar = {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "timestamp": "2025-12-01T10:00:00Z",
                "close_ts": "2025-12-01T10:00:30Z",
                "open_bid": 1.10500,
                "high_bid": 1.10600,
                "low_bid": 1.10400,
                "close_bid": 1.10550,
                "spread": 0.00012,
                "tick_volume": 100,
                "high_ask": 1.10612,
                "close_ask": 1.10562,
            }
            r = client.post("/bars", json=bar)
            assert r.status_code == 503
            assert "State manager not initialized" in r.json()["detail"]
        finally:
            server._state = original_state


# ── /trades/* ─────────────────────────────────────────────────────────


class TestTradeEndpoints:
    def test_open_trade_success(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "open_trade", return_value=123):
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                    "family": "oco_first_touch",
                },
            )
            assert r.status_code == 200
            assert r.json()["internal_trade_id"] == 123

    def test_open_trade_rejects_missing_family(self, client):
        r = client.post(
            "/trades/open",
            json={
                "symbol": "EURUSD",
                "candidate_uid": "test_cand",
                "broker_pos_id": "456",
                "side": "BUY",
                "entry_price": 1.1000,
                "entry_ts": "2025-01-01T00:00:00Z",
                "horizon": 12,
            },
        )
        assert r.status_code == 422

    def test_open_trade_passes_family(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "open_trade", return_value=123) as mock_open:
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                    "family": "directional",
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_open.call_args.kwargs
            assert call_kwargs.get("family") == "directional"

    @pytest.mark.requires_models
    def test_touch_trade_success(self, client):
        import unittest.mock as mock

        with (
            mock.patch.object(server._state, "get_latest_bar_id", return_value=999),
            mock.patch.object(server._state, "touch_trade"),
        ):
            r = client.post(
                "/trades/touch",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                },
            )
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_update_trade_success(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "update_trade"):
            r = client.post(
                "/trades/update",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                    "status": "CLOSED",
                    "family": "oco_first_touch",
                    "exit_price": 1.1050,
                    "exit_ts": "2025-01-01T02:00:00Z",
                    "pnl_pips": 50.0,
                },
            )
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

    def test_update_trade_rejects_missing_family(self, client):
        r = client.post(
            "/trades/update",
            json={
                "symbol": "EURUSD",
                "broker_pos_id": "456",
                "status": "CLOSED",
            },
        )
        assert r.status_code == 422

    def test_get_active_trades_success(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "get_active_trades", return_value=[]):
            r = client.get("/trades/active?symbol=EURUSD")
            assert r.status_code == 200
            assert r.json() == []

    def test_trade_endpoints_uninitialized_state(self, client):
        original_state = server._state
        server._state = None
        try:
            assert (
                client.post(
                    "/trades/open",
                    json={
                        "symbol": "E",
                        "candidate_uid": "C",
                        "broker_pos_id": "1",
                        "side": "BUY",
                        "entry_price": 1.0,
                        "entry_ts": "2025-01-01T00:00:00Z",
                        "horizon": 12,
                        "family": "oco_first_touch",
                    },
                ).status_code
                == 503
            )
            assert (
                client.post("/trades/touch", json={"symbol": "E", "broker_pos_id": "1"}).status_code
                == 503
            )
            assert (
                client.post(
                    "/trades/update",
                    json={
                        "symbol": "E",
                        "broker_pos_id": "1",
                        "status": "CLOSED",
                        "family": "oco_first_touch",
                    },
                ).status_code
                == 503
            )
            assert client.get("/trades/active?symbol=E").status_code == 503
        finally:
            server._state = original_state

    def test_open_trade_passes_reservation_id(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "open_trade", return_value="trade-abc") as mock_open:
            r = client.post(
                "/trades/open",
                json={
                    "symbol": "EURUSD",
                    "candidate_uid": "test_cand",
                    "broker_pos_id": "456",
                    "side": "BUY",
                    "entry_price": 1.1000,
                    "entry_ts": "2025-01-01T00:00:00Z",
                    "horizon": 12,
                    "family": "oco_first_touch",
                    "reservation_id": "res-xyz-999",
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_open.call_args.kwargs
            assert call_kwargs["reservation_id"] == "res-xyz-999"

    def test_update_trade_passes_close_reason_and_commission(self, client):
        import unittest.mock as mock

        with mock.patch.object(server._state, "update_trade") as mock_update:
            r = client.post(
                "/trades/update",
                json={
                    "symbol": "EURUSD",
                    "broker_pos_id": "456",
                    "status": "CLOSED",
                    "family": "oco_first_touch",
                    "exit_price": 1.1050,
                    "exit_ts": "2025-01-01T02:00:00Z",
                    "pnl_pips": 50.0,
                    "close_reason": "HORIZON_COMPLETED",
                    "commission_ccy": -0.46,
                },
            )
            assert r.status_code == 200
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs["close_reason"] == "HORIZON_COMPLETED"
            assert abs(call_kwargs["commission_ccy"] - (-0.46)) < 1e-9
            assert call_kwargs["symbol"] == "EURUSD"


# ── /ticks, /backfill ─────────────────────────────────────────────────


class TestIngestionEndpoints:
    def test_backfill_uninitialized(self, client):
        original_state = server._state
        server._state = None
        try:
            r = client.post("/backfill", json={"symbol": "EURUSD", "ticks": []})
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_ingest_tick_uninitialized(self, client):
        original_state = server._state
        server._state = None
        try:
            r = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "bid": 1.1,
                    "ask": 1.1,
                },
            )
            assert r.status_code == 503
        finally:
            server._state = original_state

    def test_backfill_success(self, client):
        import unittest.mock as mock

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = ["bar1", "bar2"]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=300),
        ):
            r = client.post(
                "/backfill",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:00Z",
                            "bid": 1.1,
                            "ask": 1.1,
                        },
                    ],
                },
            )
            assert r.status_code == 201
            res = r.json()
            assert res["bars_created"] == 2
            assert mock_append.call_count == 2
            assert res["warm"] is True

    def test_ingest_tick_success(self, client):
        import unittest.mock as mock

        from src.behemoth.runtime.tick_aggregator import IncomingTickBar

        dummy_agg = mock.MagicMock()
        dummy_bar = IncomingTickBar(
            symbol="EURUSD",
            bar_ticks=100,
            timestamp="2025-01-01T00:00:00Z",
            close_ts="2025-01-01T00:00:10Z",
            open_bid=1.0,
            high_bid=1.0,
            low_bid=1.0,
            close_bid=1.0,
            spread=0.0,
            tick_volume=100.0,
            hl_first=1.0,
            hl_pos_frac=0.5,
            high_ask=1.0,
            close_ask=1.0,
        )
        dummy_agg.add_ticks.return_value = [dummy_bar]

        with (
            mock.patch.dict(server._aggregators, {"EURUSD": dummy_agg}),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=150),
        ):
            r = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1,
                },
            )
            assert r.status_code == 201
            res = r.json()
            assert res["tick_accepted"] is True
            assert res["bar_completed"] is True
            assert res["completed_bar_ticks"] == [100]
            assert mock_append.call_count == 1

    def test_ingest_tick_drops_duplicate_timestamp(self, client):
        import unittest.mock as mock

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            t = {
                "symbol": "EURUSD",
                "timestamp": "2025-01-01T00:00:10Z",
                "bid": 1.1,
                "ask": 1.1001,
            }
            r1 = client.post("/ticks", json=t)
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post("/ticks", json=t)
            assert r2.status_code == 201
            body = r2.json()
            assert body["tick_accepted"] is False
            assert body["drop_reason"] == "duplicate_timestamp"
            assert body["bar_completed"] is False
            assert body["completed_bar_ticks"] == []
            assert dummy_agg.add_ticks.call_count == 1

    def test_ingest_tick_accepts_duplicate_timestamp_when_client_tick_seq_monotonic(self, client):
        import unittest.mock as mock

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            r1 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 2,
                },
            )
            assert r2.status_code == 201
            body = r2.json()
            assert body["tick_accepted"] is True
            assert body["drop_reason"] is None
            assert body["symbol_tick_seq"] == 2
            assert dummy_agg.add_ticks.call_count == 2

    def test_ingest_tick_records_raw_tick_when_enabled(self, client):
        """When record_raw_ticks is True the tick is persisted with source='live'."""
        import unittest.mock as mock

        orig_record = server._config.record_raw_ticks
        try:
            server._config.record_raw_ticks = True
            with (
                mock.patch.object(server._state, "record_raw_tick") as mock_raw,
                mock.patch.object(server._state, "bar_count", return_value=0),
                mock.patch.dict(
                    server._aggregators,
                    {100: mock.MagicMock(add_ticks=mock.MagicMock(return_value=[]))},
                    clear=True,
                ),
            ):
                r = client.post(
                    "/ticks",
                    json={
                        "symbol": "EURUSD",
                        "timestamp": "2025-01-01T00:00:00Z",
                        "bid": 1.1,
                        "ask": 1.1001,
                    },
                )
                assert r.status_code == 201
                mock_raw.assert_called_once()
                assert mock_raw.call_args.kwargs.get("source") == "live"
        finally:
            server._config.record_raw_ticks = orig_record

    def test_ingest_tick_writes_debug_http_trace(self, client, tmp_path):
        import unittest.mock as mock

        trace_path = tmp_path / "http_trace.ndjson"
        orig_record = server._config.record_raw_ticks
        orig_trace = server._config.debug_http_trace
        orig_trace_path = server._config.debug_http_trace_path
        orig_debug_run_id = server._config.debug_run_id
        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []
        try:
            server._config.record_raw_ticks = False
            server._config.debug_http_trace = True
            server._config.debug_http_trace_path = str(trace_path)
            server._config.debug_run_id = "trace_fallback_run"
            with (
                mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
                mock.patch.object(server._state, "bar_count", return_value=0),
            ):
                r = client.post(
                    "/ticks",
                    json={
                        "symbol": "EURUSD",
                        "timestamp": "2025-01-01T00:00:00Z",
                        "bid": 1.1,
                        "ask": 1.1001,
                        "client_tick_seq": 7,
                        "run_id": "tick_run_01",
                    },
                )
                assert r.status_code == 201

            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            assert len(rows) >= 3
            assert {row["phase"] for row in rows} >= {"request", "tick_result", "response"}
            assert all(row["run_id"] == "tick_run_01" for row in rows)
            assert any(
                (row.get("request") or {}).get("client_tick_seq") == 7
                for row in rows
                if isinstance(row.get("request"), dict)
            )
        finally:
            server._config.record_raw_ticks = orig_record
            server._config.debug_http_trace = orig_trace
            server._config.debug_http_trace_path = orig_trace_path
            server._config.debug_run_id = orig_debug_run_id

    def test_ingest_tick_drops_duplicate_client_tick_seq(self, client):
        import unittest.mock as mock

        dummy_agg = mock.MagicMock()
        dummy_agg.add_ticks.return_value = []

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "bar_count", return_value=0),
        ):
            r1 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:10Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r1.status_code == 201
            assert r1.json()["tick_accepted"] is True

            r2 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:11Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 1,
                },
            )
            assert r2.status_code == 201
            assert r2.json()["tick_accepted"] is False
            assert r2.json()["drop_reason"] == "duplicate_client_tick_seq"

            r3 = client.post(
                "/ticks",
                json={
                    "symbol": "EURUSD",
                    "timestamp": "2025-01-01T00:00:12Z",
                    "bid": 1.1,
                    "ask": 1.1001,
                    "client_tick_seq": 0,
                },
            )
            assert r3.status_code == 201
            assert r3.json()["tick_accepted"] is False
            assert r3.json()["drop_reason"] == "non_monotonic_client_tick_seq"

    def test_ingest_ticks_batch_success(self, client):
        import unittest.mock as mock

        from src.behemoth.runtime.tick_aggregator import IncomingTickBar

        dummy_agg = mock.MagicMock()
        dummy_bar = IncomingTickBar(
            symbol="EURUSD",
            bar_ticks=100,
            timestamp="2025-01-01T00:00:00Z",
            close_ts="2025-01-01T00:00:10Z",
            open_bid=1.0,
            high_bid=1.0,
            low_bid=1.0,
            close_bid=1.0,
            spread=0.0,
            tick_volume=100.0,
            hl_first=1.0,
            hl_pos_frac=0.5,
            high_ask=1.0,
            close_ask=1.0,
        )
        dummy_agg.add_ticks.side_effect = [[], [dummy_bar]]

        with (
            mock.patch.dict(server._aggregators, {100: dummy_agg}, clear=True),
            mock.patch.object(server._state, "append_bar") as mock_append,
            mock.patch.object(server._state, "bar_count", return_value=150),
        ):
            r = client.post(
                "/ticks/batch",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:10Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                            "client_tick_seq": 1,
                        },
                        {
                            "symbol": "EURUSD",
                            "timestamp": "2025-01-01T00:00:11Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                            "client_tick_seq": 2,
                        },
                    ],
                },
            )
            assert r.status_code == 201
            body = r.json()
            assert body["accepted_count"] == 2
            assert body["dropped_count"] == 0
            assert body["bar_completed"] is True
            assert body["completed_bar_ticks"] == [100]
            assert mock_append.call_count == 1

    def test_ingest_ticks_batch_symbol_mismatch(self, client):
        import unittest.mock as mock

        with (
            mock.patch.object(server._state, "bar_count", return_value=0),
            mock.patch.dict(
                server._aggregators,
                {100: mock.MagicMock(add_ticks=mock.MagicMock(return_value=[]))},
                clear=True,
            ),
        ):
            r = client.post(
                "/ticks/batch",
                json={
                    "symbol": "EURUSD",
                    "ticks": [
                        {
                            "symbol": "GBPUSD",
                            "timestamp": "2025-01-01T00:00:10Z",
                            "bid": 1.1,
                            "ask": 1.1001,
                        }
                    ],
                },
            )
            assert r.status_code == 422


# ── /state/checkpoint ─────────────────────────────────────────────────


class TestCheckpointEndpoint:
    def test_checkpoint_returns_ok(self, client):
        r = client.get("/state/checkpoint")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "checkpointed_at" in body

    def test_checkpoint_503_when_state_uninitialized(self, client):
        original = server._state
        server._state = None
        try:
            r = client.get("/state/checkpoint")
            assert r.status_code == 503
        finally:
            server._state = original


# ── /trades/open-summary ──────────────────────────────────────────────


class TestOpenSummaryEndpoint:
    def test_fx_snapshot_and_conversion_use_canonical_close_bid_schema(self):
        from src.behemoth.core.schemas import IncomingTickBar
        from src.behemoth.runtime.state import StateManager

        original_state = server._state
        server._state = StateManager()
        try:
            server._state.append_bar(
                IncomingTickBar(
                    symbol="USDJPY",
                    bar_ticks=100,
                    timestamp=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
                    close_ts=datetime(2026, 4, 10, 10, 1, tzinfo=timezone.utc),
                    open_bid=145.10,
                    high_bid=145.22,
                    low_bid=145.05,
                    close_bid=145.20,
                    spread=0.02,
                    tick_volume=100.0,
                    high_ask=145.24,
                    close_ask=145.22,
                )
            )

            snapshot = server._latest_tick_price_snapshot("USDJPY")
            conversion = server._pip_value_per_unit_usd(
                "USDJPY",
                now_utc=datetime(2026, 4, 10, 10, 1, 30, tzinfo=timezone.utc),
                max_age_sec=300,
            )

            assert snapshot is not None
            assert snapshot["price"] == pytest.approx(145.20)
            assert conversion["conversion_status"] == "direct_base_usd"
            assert conversion["conversion_pair"] == "USDJPY"
            assert conversion["conversion_rate"] == pytest.approx(145.20)
            assert conversion["pip_value_per_unit_usd"] == pytest.approx(0.01 / 145.20)
        finally:
            server._state = original_state

    def test_open_summary_empty(self, client):
        """No open reservations → empty positions list."""
        r = client.get("/trades/open-summary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_open"] == 0
        assert body["broker_confirmed"] == 0
        assert body["pending_broker_confirm"] == 0
        assert body["positions"] == []
        assert "as_of_utc" in body

    def test_get_last_bar_close_price_returns_none_when_no_bars(self, client):
        """StateManager returns None when tick_bars has no rows for symbol."""
        result = server._state.get_last_bar_close_price("EURUSD")
        assert result is None

    def test_build_summary_with_pending_reservation(self, client):
        """PENDING reservation with no broker_pos_id → entry_price null, unrealized null."""
        import unittest.mock as mock

        now = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
        created = now - timedelta(minutes=12, seconds=30)
        fake_reservation = {
            "reservation_id": "res-001",
            "created_ts": created,
            "updated_ts": created,
            "symbol": "USDCHF",
            "candidate_uid": "cand-001",
            "broker_pos_id": None,
            "status": "PENDING",
            "reserved_loss_ccy": 10.0,
            "barrier_pips": 20.0,
            "cap_pips": 30.0,
            "cost_est_pips": 5.0,
            "volume_units": 1000.0,
            "side": "BUY",
            "source": "algo",
        }
        with (
            mock.patch.object(
                server._state,
                "list_active_account_risk_reservations",
                return_value=[fake_reservation],
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(server._state, "get_all_symbols", return_value=["USDCHF"]),
        ):
            summary = server._build_open_positions_summary(server._state, now)

        assert summary["total_open"] == 1
        assert summary["broker_confirmed"] == 0
        assert summary["pending_broker_confirm"] == 1
        pos = summary["positions"][0]
        assert pos["symbol"] == "USDCHF"
        assert pos["status"] == "PENDING"
        assert pos["broker_confirmed"] is False
        assert pos["broker_pos_id"] is None
        assert pos["entry_price"] is None
        assert pos["estimated_unrealized_pips"] is None
        assert pos["open_minutes"] == 12.5

    def test_open_summary_with_pending_reservation(self, client):
        """Endpoint returns one PENDING position with correct shape."""
        import unittest.mock as mock

        now_fixed = datetime(2026, 4, 7, 14, 15, 0, tzinfo=timezone.utc)
        created = now_fixed - timedelta(minutes=5)
        fake_reservation = {
            "reservation_id": "res-001",
            "created_ts": created,
            "updated_ts": created,
            "symbol": "EURUSD",
            "candidate_uid": "cand-001",
            "broker_pos_id": None,
            "status": "PENDING",
            "reserved_loss_ccy": 10.0,
            "barrier_pips": 20.0,
            "cap_pips": 30.0,
            "cost_est_pips": 5.0,
            "volume_units": 1000.0,
            "side": "BUY",
            "source": "algo",
        }
        with (
            mock.patch.object(
                server._state,
                "list_active_account_risk_reservations",
                return_value=[fake_reservation],
            ),
            mock.patch.object(server._state, "get_last_bar_close_price", return_value=None),
            mock.patch.object(server._state, "get_all_symbols", return_value=["EURUSD"]),
        ):
            r = client.get("/trades/open-summary")

        assert r.status_code == 200
        body = r.json()
        assert body["total_open"] == 1
        assert body["pending_broker_confirm"] == 1
        assert len(body["positions"]) == 1
        pos = body["positions"][0]
        assert pos["symbol"] == "EURUSD"
        assert pos["status"] == "PENDING"
        assert pos["broker_confirmed"] is False
        assert pos["entry_price"] is None
        assert pos["estimated_unrealized_pips"] is None

    def test_open_summary_uninitialized_state(self, client):
        """Returns 503 when state manager is not initialized."""
        original = server._state
        server._state = None
        try:
            r = client.get("/trades/open-summary")
            assert r.status_code == 503
        finally:
            server._state = original

    def test_position_summary_writer_skips_without_persist_path(self, client):
        """Writer loop body does not write when persist_db_path is falsy."""
        import asyncio
        import unittest.mock as mock

        original_path = server._config.persist_db_path
        written_paths: list[str] = []
        real_write_text = Path.write_text

        def tracking_write_text(self, *args, **kwargs):
            written_paths.append(str(self))
            return real_write_text(self, *args, **kwargs)

        server._config.persist_db_path = ""
        try:
            with mock.patch.object(Path, "write_text", tracking_write_text):
                coro = server._write_position_summary_loop()
                try:
                    loop = asyncio.new_event_loop()
                    task = loop.create_task(coro)
                    loop.call_soon(task.cancel)
                    loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
                    loop.close()
                except Exception:
                    pass
        finally:
            server._config.persist_db_path = original_path

        assert not any("live_position_summary" in p for p in written_paths)
