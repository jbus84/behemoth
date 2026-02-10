from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.db import Base, get_db
from services.api.settings import settings
from services.api.main import app
from services.api.models import PositionStatus, Side, ActiveLeg


def make_client():
    settings.enable_redis = False
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_position_lifecycle():
    client = make_client()
    payload = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
        "size": 1.0,
        "metadata": {"z": 1.7},
    }
    resp = client.post("/positions", json=payload)
    assert resp.status_code == 200
    pos = resp.json()
    assert pos["status"] == PositionStatus.PENDING

    open_resp = client.post(f"/positions/{pos['id']}/open", json={"entry_price": 1.234})
    assert open_resp.status_code == 200
    assert open_resp.json()["status"] == PositionStatus.OPEN

    close_resp = client.post(
        f"/positions/{pos['id']}/close", json={"exit_price": 1.235, "pnl_bps": 10.0}
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["status"] == PositionStatus.CLOSED


def test_idempotency_key():
    client = make_client()
    payload = {
        "strategy_id": "mom_m15",
        "pair": "Gold/Oil",
        "side": Side.SHORT,
        "active_leg": ActiveLeg.X,
        "size": 2.0,
    }
    headers = {"Idempotency-Key": "abc123"}
    resp1 = client.post("/positions", json=payload, headers=headers)
    resp2 = client.post("/positions", json=payload, headers=headers)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


def test_invalid_transition():
    client = make_client()
    payload = {
        "strategy_id": "mom_m15",
        "pair": "Gold/Oil",
        "side": Side.SHORT,
        "active_leg": ActiveLeg.X,
        "size": 2.0,
    }
    resp = client.post("/positions", json=payload)
    pos = resp.json()

    close_resp = client.post(
        f"/positions/{pos['id']}/close", json={"exit_price": 1.1, "pnl_bps": -5.0}
    )
    assert close_resp.status_code == 409
