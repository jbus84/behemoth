from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pandas as pd

from services.api.db import Base
from services.api.models import Position, PositionStatus, Side, ActiveLeg
from services.api import validation


def test_db_matches_pipeline_with_ts_matching(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    # pipeline sample
    df = pd.DataFrame(
        {
            "pair": ["EUR/GBP", "EUR/GBP"],
            "timestamp": [0, 1_000_000_000],
            "duration_bars": [1, 1],
            "pnl_bps": [2.0, -1.0],
            "side": ["LONG", "LONG"],
            "active_leg": ["Y", "Y"],
        }
    )
    path = tmp_path / "events.csv"
    df.to_csv(path, index=False)
    validation.PIPELINE_PATHS["m5"] = str(path)

    with Session() as session:
        bar_ns = int(pd.Timedelta(minutes=5).value)
        for row in df.itertuples(index=False):
            exit_ts = int(row.timestamp) + bar_ns
            session.add(
                Position(
                    strategy_id="pipeline_m5",
                    pair=row.pair,
                    side=Side(row.side),
                    active_leg=ActiveLeg(row.active_leg),
                    status=PositionStatus.CLOSED,
                    size=1.0,
                    pnl_bps=float(row.pnl_bps),
                    exit_ts=pd.to_datetime(exit_ts, unit="ns", utc=True),
                )
            )
        session.commit()

        res = validation.compare_pipeline_to_db(
            session,
            "m5",
            match_ts=True,
            ts_tolerance_ns=1000,
            match_pair=True,
        )
        assert res["within_tolerance"] is True
