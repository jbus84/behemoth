from fastapi.testclient import TestClient
from services.api.main import app
from services.api.signals import STATE_KALMAN

client = TestClient(app)

def test_self_healing_409():
    state_key = "mom_m5"
    # Ensure state is empty
    if state_key in STATE_KALMAN:
        del STATE_KALMAN[state_key]
    
    # Send incremental payload (1 bar)
    payload = {
        "bars": {
            "EUR/USD": [1.0500]
        },
        "current_time": "2025-01-01T12:00:00Z",
        "equity": 10000.0
    }
    
    response = client.post("/signals/m5", json=payload)
    
    assert response.status_code == 409
    assert response.json()["detail"] == "State missing. Please resend full history."
