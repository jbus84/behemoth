import json
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


def test_position_sizing_enforced():
    client = make_client()
    settings.guardrail_enabled = False
    settings.account_equity_start = 100000
    settings.max_total_exposure_pct = 1.0
    settings.max_pair_exposure_pct = 0.10
    settings.max_weight_overshoot_pct = 0.10

    base = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
    }

    ok = client.post("/positions", json={**base, "size": 3000.0})
    assert ok.status_code == 200

    too_big = client.post("/positions", json={**base, "size": 8000.0})
    assert too_big.status_code == 409
    assert too_big.json()["detail"]["error"] in ("max_pair_exposure", "max_total_exposure")


def test_daily_loss_killswitch(tmp_path):
    client = make_client()
    settings.guardrail_enabled = False
    settings.account_equity_start = 100000
    settings.max_total_exposure_pct = 1.0
    settings.max_pair_exposure_pct = 1.0
    settings.max_weight_overshoot_pct = 10.0
    settings.max_daily_loss_pct = 0.05
    settings.max_dd_pct = 0.10
    settings.max_consecutive_losses = 5

    weights_path = tmp_path / "weights.json"
    weights_path.write_text(json.dumps({"EUR/GBP": 1.0}))
    settings.pair_weights_path = str(weights_path)

    base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
        "size": 100000.0,
        "entry_ts": base_ts.isoformat(),
    }
    resp = client.post("/positions", json=payload)
    assert resp.status_code == 200
    pos = resp.json()
    client.post(
        f"/positions/{pos['id']}/open",
        json={"entry_price": 1.234, "entry_ts": base_ts.isoformat()},
    )
    # -6% loss on full notional triggers daily loss halt
    close_resp = client.post(
        f"/positions/{pos['id']}/close",
        json={
            "exit_price": 1.200,
            "pnl_bps": -600.0,
            "exit_ts": (base_ts + timedelta(hours=1)).isoformat(),
        },
    )
    assert close_resp.status_code == 200

    blocked = client.post("/positions", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "risk_halted"

    status = client.get("/risk/mom_m5")
    assert status.status_code == 200
    assert status.json()["halted"] is True


def test_manual_halt_and_resume():
    client = make_client()
    resp = client.post("/risk/mom_m5/halt", json={"reason": "ops_test"})
    assert resp.status_code == 200
    assert resp.json()["halted"] is True
    assert resp.json()["halt_reason"] == "ops_test"

    resume = client.post("/risk/mom_m5/resume")
    assert resume.status_code == 200
    assert resume.json()["halted"] is False
