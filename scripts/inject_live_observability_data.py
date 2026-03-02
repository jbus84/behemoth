"""Live Data Injector for Behemoth Observability Verification.

Pumps real HTTP requests into the running API at http://localhost:8001
to verify that the Docker-based Prometheus/Grafana stack captures the data.
"""

import requests
import time
import random
from datetime import datetime, timezone

BASE_URL = "http://localhost:8001"
SYMBOL = "EURUSD"

def inject_data():
    print(f"🚀 Starting Live Injection for {SYMBOL}...")
    
    # 1. Ingest Ticks
    print("Step 1: Ingesting 50 ticks...")
    for i in range(50):
        tick = {
            "symbol": SYMBOL,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "bid": 1.0850 + (i * 0.0001),
            "ask": 1.0851 + (i * 0.0001),
        }
        resp = requests.post(f"{BASE_URL}/ticks", json=tick)
        if resp.status_code != 201:
            print(f"❌ Tick error: {resp.text}")
    
    # 2. Trigger Predictions (Latency Histogram)
    print("Step 2: Triggering 5 predictions...")
    for _ in range(5):
        requests.post(f"{BASE_URL}/predict", json={"symbol": SYMBOL})
        time.sleep(0.5)

    # 3. Simulate Trade Lifecycle
    pos_id = f"live_pos_{int(time.time())}"
    print(f"Step 3: Opening Trade {pos_id}...")
    trade_req = {
        "symbol": SYMBOL,
        "candidate_uid": "live|verify|1",
        "broker_pos_id": pos_id,
        "side": "BUY",
        "entry_price": 1.0850,
        "entry_ts": datetime.now(tz=timezone.utc).isoformat(),
        "horizon": 12
    }
    requests.post(f"{BASE_URL}/trades/open", json=trade_req)
    
    time.sleep(2)  # Wait for ledger sync (60s loop, but stats are immediate in memory)

    print(f"Step 4: Closing Trade {pos_id} with profit...")
    update_req = {
        "symbol": SYMBOL,
        "broker_pos_id": pos_id,
        "status": "CLOSED",
        "exit_price": 1.0875,
        "exit_ts": datetime.now(tz=timezone.utc).isoformat(),
        "pnl_pips": 25.0
    }
    requests.post(f"{BASE_URL}/trades/update", json=update_req)

    print("✅ Injection Complete. Metrics should update in Prometheus shortly.")

if __name__ == "__main__":
    try:
        inject_data()
    except Exception as e:
        print(f"❌ Error: {e}")
