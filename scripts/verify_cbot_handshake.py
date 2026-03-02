import json
import logging
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from src.behemoth.api.server import app

def test_horizon_ledger():
    with TestClient(app) as client:
        # 1. Health
        resp = client.get("/health")
        print(f"API Health: {resp.json().get('status')}")
        assert resp.status_code == 200

        # 2. Trade Open with Horizon
        # Note: server.py open_trade will look for tick_bars to get entry_bar_id.
        # We assume tick_bars exists or defaults to 0.
        resp = client.post("/trades/open", json={
            "symbol": "EURUSD",
            "candidate_uid": "test_cand",
            "broker_pos_id": "88888",
            "side": "Buy",
            "entry_price": 1.1000,
            "entry_ts": datetime.now(timezone.utc).isoformat(),
            "horizon": 24
        })
        print(f"Trade Open (Horizon=24): {resp.status_code}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 3. State Recovery (GET /trades/active)
        resp = client.get("/trades/active?symbol=EURUSD")
        print(f"Recovery Endpoint: {resp.status_code}")
        assert resp.status_code == 200
        active = resp.json()
        
        found = [t for t in active if t["broker_pos_id"] == "88888"]
        assert len(found) == 1
        assert found[0]["horizon"] == 24
        print(f"SUCCESS: Recovered horizon {found[0]['horizon']} for trade 88888")

        # 4. Trade Update (Close)
        resp = client.post("/trades/update", json={
            "broker_pos_id": "88888",
            "status": "CLOSED",
            "exit_price": 1.1020,
            "exit_ts": datetime.now(timezone.utc).isoformat(),
            "pnl_pips": 20.0
        })
        assert resp.status_code == 200

    print("ALL HORIZON LEDGER TESTS PASSED")

if __name__ == "__main__":
    test_horizon_ledger()
