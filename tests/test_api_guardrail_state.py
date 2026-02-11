from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.db import Base, get_db
from services.api.main import app
from services.api.models import ActiveLeg, Side
from services.api.settings import settings


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


def test_guardrail_blocks_after_losses():
    client = make_client()
    settings.guardrail_enabled = True
    settings.guardrail_loss_streak = 2
    settings.guardrail_cooldown_days = 1
    settings.guardrail_loss_threshold = 0.0

    base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def _open_close(idx: int, pnl: float):
        payload = {
            "strategy_id": "mom_m5",
            "pair": "EUR/GBP",
            "side": Side.LONG,
            "active_leg": ActiveLeg.Y,
            "size": 1.0,
            "entry_ts": (base_ts + timedelta(minutes=idx)).isoformat(),
        }
        resp = client.post("/positions", json=payload)
        assert resp.status_code == 200
        pos = resp.json()
        client.post(
            f"/positions/{pos['id']}/open",
            json={"entry_price": 1.234, "entry_ts": base_ts.isoformat()},
        )
        close_resp = client.post(
            f"/positions/{pos['id']}/close",
            json={
                "exit_price": 1.233,
                "pnl_bps": pnl,
                "exit_ts": (base_ts + timedelta(minutes=idx)).isoformat(),
            },
        )
        assert close_resp.status_code == 200

    _open_close(0, -5.0)
    _open_close(1, -4.0)

    blocked_payload = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
        "size": 1.0,
        "entry_ts": (base_ts + timedelta(hours=1)).isoformat(),
    }
    blocked = client.post("/positions", json=blocked_payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "guardrail_paused"

    allowed_payload = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
        "size": 1.0,
        "entry_ts": (base_ts + timedelta(days=2)).isoformat(),
    }
    allowed = client.post("/positions", json=allowed_payload)
    assert allowed.status_code == 200


def test_guardrail_status_endpoint():
    client = make_client()
    settings.guardrail_enabled = True
    resp = client.get("/guardrail/mom_m5/EUR%2FGBP")
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy_id"] == "mom_m5"
    assert data["pair"] == "EUR/GBP"
    assert data["can_trade"] is True
