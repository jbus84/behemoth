import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.api import validation
from services.api.db import Base, get_db
from services.api.main import app
from services.api.models import ActiveLeg, Position, PositionStatus, Side
from services.api.settings import settings


def make_client(engine):
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_compare_endpoint(tmp_path):
    settings.enable_redis = False
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    # Seed DB positions
    db = sessionmaker(bind=engine)()
    bar_ns = int(pd.Timedelta(minutes=5).value)
    db.add(
        Position(
            strategy_id="mom_m5",
            pair="EUR/GBP",
            side=Side.LONG,
            active_leg=ActiveLeg.Y,
            status=PositionStatus.CLOSED,
            size=1.0,
            pnl_bps=2.0,
            exit_ts=pd.to_datetime(bar_ns, unit="ns", utc=True),
        )
    )
    db.add(
        Position(
            strategy_id="mom_m5",
            pair="EUR/GBP",
            side=Side.LONG,
            active_leg=ActiveLeg.Y,
            status=PositionStatus.CLOSED,
            size=1.0,
            pnl_bps=-1.0,
            exit_ts=pd.to_datetime(bar_ns + 1_000_000_000, unit="ns", utc=True),
        )
    )
    db.commit()
    db.close()

    # Seed pipeline CSV
    df = pd.DataFrame(
        {
            "timestamp": [0, 1_000_000_000],
            "duration_bars": [1, 1],
            "pnl_bps": [2.0, -1.0],
            "pair": ["EUR/GBP", "EUR/GBP"],
        }
    )
    path = tmp_path / "events.csv"
    df.to_csv(path, index=False)
    validation.PIPELINE_PATHS["m5"] = str(path)

    client = make_client(engine)
    resp = client.get(
        "/validation/compare/m5",
        params={"match_ts": True, "ts_tolerance_ns": 1000, "match_pair": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["within_tolerance"] is True
    assert data["pipeline"]["trades"] == 2
    assert data["db"]["trades"] == 2
