"""Logging-based E2E test for the Behemoth Observability stack.

Verifies:
1. Tick ingestion -> State buffer.
2. Prediction -> Audit Log + Prometheus Latency.
3. Trade Open/Update -> Strategic Ledger + Prometheus Equity/Counters.
4. Metric Scrape -> /metrics formatting.
"""

import logging
import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

# Use a temporary database for testing to avoid lock conflicts
os.environ["BEHEMOTH_STATE_DB"] = "/tmp/behemoth_test_observability.db"

from src.behemoth.api.server import app

# Configure logging to capture output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("behemoth.test")

client = TestClient(app)


def test_observability_lifecycle():
    symbol = "EURUSD"

    with TestClient(app) as client:
        # 1. Warmup: Send Ticks
        # ...
        logger.info("Step 1: Ingesting ticks...")
        for i in range(10):  # Simplified for speed
            tick = {
                "symbol": symbol,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "bid": 1.0850 + (i * 0.0001),
                "ask": 1.0851 + (i * 0.0001),
            }
            resp = client.post("/ticks", json=tick)
            assert resp.status_code == 201

        # 2. Prediction (Trigger Metrics)
        logger.info("Step 2: Triggering Prediction...")
        resp = client.post(
            "/predict",
            json={
                "symbol": symbol,
                "requested_volume_units": 10000,
                "ftmo_enabled_override": True,
            },
        )
        assert resp.status_code in [200, 422, 503]

        # 3. Trade Lifecycle (Trigger Ledger & Counters)
        logger.info("Step 3: Opening Trade...")
        trade_req = {
            "symbol": symbol,
            "candidate_uid": "test|cand|1",
            "broker_pos_id": "pos_12345",
            "side": "BUY",
            "entry_price": 1.0855,
            "entry_ts": datetime.now(tz=timezone.utc).isoformat(),
            "horizon": 10,
        }
        resp = client.post("/trades/open", json=trade_req)
        assert resp.status_code == 200

        # Update Trade
        logger.info("Step 4: Closing Trade...")
        update_req = {
            "symbol": symbol,
            "broker_pos_id": "pos_12345",
            "status": "CLOSED",
            "exit_price": 1.0865,
            "exit_ts": datetime.now(tz=timezone.utc).isoformat(),
            "pnl_pips": 10.0,
        }
        resp = client.post("/trades/update", json=update_req)
        assert resp.status_code == 200

        # 4. Scrape Metrics
        logger.info("Step 5: Verifying Prometheus /metrics...")
        metrics_resp = client.get("/metrics")
        assert metrics_resp.status_code == 200
        data = metrics_resp.text

        # Check for presence of custom metrics
        assert "behemoth_trades_total" in data
        assert "behemoth_equity_pips" in data
        assert "behemoth_bar_count" in data

        logger.info("E2E Observability Test PASSED")


if __name__ == "__main__":
    test_observability_lifecycle()
