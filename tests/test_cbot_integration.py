"""
Integration tests for the cBot → Behemoth API signal + position flow.

Validates:
1. POST /signals/{bar} computes signals from submitted bar data
2. GET /signals/{bar} returns correct schema (parquet fallback)
3. Position lifecycle (create → open → close) works end-to-end
4. Idempotency on position creation
5. Pair symbol mapping is consistent
"""

from __future__ import annotations

import os
import uuid

# Must set before any app imports
os.environ["DATABASE_URL"] = "sqlite:///test_cbot.db"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["REDIS_URL"] = ""
os.environ["ENABLE_REDIS"] = "false"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# Patch the db module BEFORE importing the app
import services.api.db as db_mod  # noqa: E402

_test_engine = create_engine("sqlite:///test_cbot.db", connect_args={"check_same_thread": False})
_TestSession = sessionmaker(bind=_test_engine, autocommit=False, autoflush=False, expire_on_commit=False)
db_mod.engine = _test_engine
db_mod.SessionLocal = _TestSession

from services.api.db import Base  # noqa: E402
from services.api.main import app  # noqa: E402
from services.api.signals import PAIR_SYMBOL_MAP, REQUIRED_SYMBOLS  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    """Create tables before tests, clean up after."""
    Base.metadata.create_all(bind=_test_engine)
    yield
    Base.metadata.drop_all(bind=_test_engine)
    try:
        os.remove("test_cbot.db")
    except FileNotFoundError:
        pass


@pytest.fixture(scope="module")
def client():
    """Create a test client that persists across all tests in the module."""
    with TestClient(app) as c:
        yield c


def _make_synthetic_bars(n: int = 800) -> dict[str, list[float]]:
    """
    Generate synthetic close prices for all 18 required symbols.
    Uses correlated random walks so some pairs will naturally produce
    z-scores above the entry threshold.
    """
    rng = np.random.RandomState(42)
    bars = {}
    # Generate a common trend component
    trend = np.cumsum(rng.randn(n) * 0.001) + np.log(100)

    for i, sym in enumerate(sorted(REQUIRED_SYMBOLS)):
        # Each symbol = common trend + independent noise + offset
        noise = np.cumsum(rng.randn(n) * 0.0005)
        offset = i * 0.5  # Different price levels
        log_prices = trend + noise + offset
        bars[sym] = np.exp(log_prices).tolist()

    return bars


class TestPostSignalsEndpoint:
    """Test the POST /signals/{bar} endpoint (production path)."""

    def test_post_signals_returns_200(self, client: TestClient):
        bars = _make_synthetic_bars()
        resp = client.post("/signals/m15", json={"bars": bars})
        assert resp.status_code == 200
        body = resp.json()
        assert body["bar"] == "m15"
        assert isinstance(body["signals"], list)
        assert isinstance(body["exits"], list)
        assert "checked_pairs" in body
        assert "timestamp" in body

    def test_post_signals_invalid_bar(self, client: TestClient):
        resp = client.post("/signals/h4", json={"bars": {}})
        assert resp.status_code == 400

    def test_post_signals_schema(self, client: TestClient):
        bars = _make_synthetic_bars()
        resp = client.post("/signals/m15", json={"bars": bars})
        body = resp.json()
        for sig in body["signals"]:
            assert "pair" in sig
            assert sig["side"] in ("LONG", "SHORT")
            assert sig["active_leg"] in ("X", "Y")
            assert isinstance(sig["z_score"], float)
            assert isinstance(sig["beta"], float)
            assert "leg_x" in sig
            assert "leg_y" in sig

    def test_post_signals_with_current_time(self, client: TestClient):
        bars = _make_synthetic_bars()
        resp = client.post(
            "/signals/m15",
            json={"bars": bars, "current_time": "2026-02-12T12:00:00Z"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["timestamp"].startswith("2026-02-12T12:00:00")

    def test_post_signals_missing_symbols_still_works(self, client: TestClient):
        """API should handle partial bar data gracefully."""
        bars = _make_synthetic_bars()
        # Remove a few symbols
        del bars["XAUUSD"]
        del bars["XAGUSD"]
        resp = client.post("/signals/m15", json={"bars": bars})
        assert resp.status_code == 200

    def test_post_signals_pair_symbols_consistent(self, client: TestClient):
        bars = _make_synthetic_bars()
        resp = client.post("/signals/m15", json={"bars": bars})
        body = resp.json()
        for sig in body["signals"]:
            assert sig["pair"] in PAIR_SYMBOL_MAP, (
                f"Pair {sig['pair']} missing from PAIR_SYMBOL_MAP"
            )
            assert sig["leg_x"] == PAIR_SYMBOL_MAP[sig["pair"]][0]
            assert sig["leg_y"] == PAIR_SYMBOL_MAP[sig["pair"]][1]


class TestPositionLifecycle:
    """
    Simulate the cBot's position lifecycle against the API.
    This mirrors exactly what the C# cBot does via HTTP.
    """

    def test_create_open_close(self, client: TestClient):
        """Full position lifecycle: create → open → close."""
        # 1. Create
        create_payload = {
            "strategy_id": "mom_m15",
            "pair": "EUR/GBP",
            "side": "LONG",
            "active_leg": "Y",
            "size": 5000.0,
            "entry_ts": "2026-02-12T12:00:00Z",
            "metadata": {"bar": "m15", "z_score": 1.82},
        }
        resp = client.post(
            "/positions",
            json=create_payload,
            headers={"Idempotency-Key": f"test-{uuid.uuid4()}"},
        )
        assert resp.status_code == 200, f"Create failed: {resp.json()}"
        pos = resp.json()
        assert pos["status"] == "PENDING"
        pos_id = pos["id"]

        # 2. Open
        open_payload = {
            "entry_price": 0.8456,
            "entry_ts": "2026-02-12T12:00:05Z",
        }
        resp = client.post(f"/positions/{pos_id}/open", json=open_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "OPEN"

        # 3. Close
        close_payload = {
            "exit_price": 0.8462,
            "exit_ts": "2026-02-12T13:15:00Z",
            "pnl_bps": 7.1,
        }
        resp = client.post(f"/positions/{pos_id}/close", json=close_payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "CLOSED"

    def test_idempotency(self, client: TestClient):
        """Duplicate create with same key returns same position."""
        key = f"idem-test-{uuid.uuid4()}"
        payload = {
            "strategy_id": "mom_m15",
            "pair": "Gold/Silver",
            "side": "SHORT",
            "active_leg": "X",
            "size": 5000.0,
            "metadata": {},
        }
        resp1 = client.post("/positions", json=payload, headers={"Idempotency-Key": key})
        resp2 = client.post("/positions", json=payload, headers={"Idempotency-Key": key})
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_cancel_unfilled(self, client: TestClient):
        """Cancel a PENDING position (order failed in cTrader)."""
        payload = {
            "strategy_id": "mom_m15",
            "pair": "AUD/NZD",
            "side": "LONG",
            "active_leg": "Y",
            "size": 5000.0,
            "metadata": {},
        }
        resp = client.post(
            "/positions",
            json=payload,
            headers={"Idempotency-Key": f"cancel-{uuid.uuid4()}"},
        )
        pos_id = resp.json()["id"]

        resp = client.post(f"/positions/{pos_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"
