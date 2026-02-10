import os
import pytest
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.api.db import Base, get_db
from services.api.main import app
from services.api.models import Position, PositionStatus, Side, ActiveLeg
from services.api.settings import settings
from services.api import validation


POSTGRES_URL = os.getenv("POSTGRES_TEST_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="POSTGRES_TEST_URL not set")
def test_postgres_api_and_compare(tmp_path):
    settings.enable_redis = False
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Clean tables
    with Session() as session:
        session.execute(
            text(
                "TRUNCATE positions, orders, position_events, idempotency_keys, guardrail_state, account_state RESTART IDENTITY"
            )
        )
        session.commit()

    client = TestClient(app)

    payload = {
        "strategy_id": "mom_m5",
        "pair": "EUR/GBP",
        "side": Side.LONG,
        "active_leg": ActiveLeg.Y,
        "size": 1.0,
    }
    resp = client.post("/positions", json=payload)
    assert resp.status_code == 200
    pos = resp.json()

    open_resp = client.post(f"/positions/{pos['id']}/open", json={"entry_price": 1.234})
    assert open_resp.status_code == 200

    close_resp = client.post(
        f"/positions/{pos['id']}/close", json={"exit_price": 1.235, "pnl_bps": 2.0}
    )
    assert close_resp.status_code == 200

    # Seed pipeline CSV with matching PnL for comparison
    df = pd.DataFrame(
        {
            "pair": ["EUR/GBP"],
            "timestamp": [0],
            "duration_bars": [1],
            "pnl_bps": [2.0],
            "side": ["LONG"],
            "active_leg": ["Y"],
        }
    )
    path = tmp_path / "events.csv"
    df.to_csv(path, index=False)
    validation.PIPELINE_PATHS["m5"] = str(path)

    resp = client.get(
        "/validation/compare/m5",
        params={"match_ts": False},
    )
    assert resp.status_code == 200
