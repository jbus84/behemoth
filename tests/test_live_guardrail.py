
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from services.api.db import Base
from services.api.models import Position, PositionStatus, ActiveLeg, Side
from services.api.signals import _check_guardrail
from behemoth.config import LOSS_STREAK, COOLDOWN_DAYS

# Setup in-memory DB
engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=engine)

@pytest.fixture
def db():
    session = TestingSessionLocal()
    # clean table
    session.query(Position).delete()
    session.commit()
    try:
        yield session
    finally:
        session.close()

def create_pos(db, pair, strat, pnl, days_ago):
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    pos = Position(
        pair=pair,
        strategy_id=strat,
        side=Side.LONG,
        active_leg=ActiveLeg.Y,
        status=PositionStatus.CLOSED,
        size=1000.0,
        entry_ts=ts - timedelta(hours=1),
        exit_ts=ts,
        pnl_bps=pnl
    )
    db.add(pos)
    db.commit()
    return pos

def test_guardrail_blocks_streak(db):
    # Create 3 losses for EUR/GBP in last 1 day
    for i in range(LOSS_STREAK):
        create_pos(db, "EUR/GBP", "mom_m5", -10.0, days_ago=0.1 * (i+1))
    
    # Should be blocked
    assert _check_guardrail(db, "mom_m5", "EUR/GBP") is True

def test_guardrail_allows_mixed(db):
    # 2 losses, 1 win
    create_pos(db, "EUR/GBP", "mom_m5", -10.0, days_ago=3)
    create_pos(db, "EUR/GBP", "mom_m5", -10.0, days_ago=2)
    create_pos(db, "EUR/GBP", "mom_m5", 10.0, days_ago=1)
    
    # Should allow
    assert _check_guardrail(db, "mom_m5", "EUR/GBP") is False

def test_guardrail_allows_expired(db):
    # 3 losses, but > cooldown days ago
    for i in range(LOSS_STREAK):
        create_pos(db, "EUR/GBP", "mom_m5_exp", -10.0, days_ago=COOLDOWN_DAYS + 1)
        
    # Should allow
    assert _check_guardrail(db, "mom_m5_exp", "EUR/GBP") is False

def test_guardrail_strategy_isolation(db):
    # 3 losses for M5
    for i in range(LOSS_STREAK):
        create_pos(db, "EUR/GBP", "mom_m5", -10.0, days_ago=1)
    
    # Start checking M15 (should not be blocked by M5 losses if prefix matches?)
    # Wait, check_guardrail logic is: strategy_id.like(f"{prefix}%")
    # If prefix is "mom_m15", it won't match "mom_m5".
    
    assert _check_guardrail(db, "mom_m5", "EUR/GBP") is True
    assert _check_guardrail(db, "mom_m15", "EUR/GBP") is False
