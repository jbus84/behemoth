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


class TestPredictEndpoint:
    def test_predict_insufficient_warmup(self, client):
        """With no bars ingested, predict should return 422."""
        r = client.post("/predict", json={
            "symbol": "EURUSD",
        })
        assert r.status_code in (422, 503)
        detail = r.json()["detail"].lower()
        assert "warmup" in detail or "candidate" in detail or "registry" in detail or "model" in detail


class TestReloadEndpoint:
    def test_reload_returns_ok(self, client):
        r = client.post("/reload")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
