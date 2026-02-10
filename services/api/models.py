import enum
import uuid
from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Enum, JSON, func, UniqueConstraint, Date, Boolean
from sqlalchemy.orm import relationship

from .db import Base


class PositionStatus(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class Side(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ActiveLeg(str, enum.Enum):
    X = "X"
    Y = "Y"


class Position(Base):
    __tablename__ = "positions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String, nullable=False)
    pair = Column(String, nullable=False)
    side = Column(Enum(Side), nullable=False)
    active_leg = Column(Enum(ActiveLeg), nullable=False)
    status = Column(Enum(PositionStatus), nullable=False, default=PositionStatus.PENDING)
    entry_ts = Column(DateTime(timezone=True))
    exit_ts = Column(DateTime(timezone=True))
    entry_price = Column(Float)
    exit_price = Column(Float)
    size = Column(Float, nullable=False)
    notional_usd = Column(Float)
    alloc_frac = Column(Float)
    entry_equity = Column(Float)
    pnl_bps = Column(Float)
    meta = Column("metadata", JSON, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    orders = relationship("Order", back_populates="position")
    events = relationship("PositionEvent", back_populates="position")


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id = Column(String, ForeignKey("positions.id"), nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.NEW)
    order_type = Column(Enum(OrderType), nullable=False, default=OrderType.MARKET)
    qty = Column(Float, nullable=False)
    price = Column(Float)
    slippage_bps = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    position = relationship("Position", back_populates="orders")


class PositionEvent(Base):
    __tablename__ = "position_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    position_id = Column(String, ForeignKey("positions.id"), nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    position = relationship("Position", back_populates="events")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String, unique=True, nullable=False)
    request_hash = Column(String, nullable=False)
    position_id = Column(String, ForeignKey("positions.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GuardrailState(Base):
    __tablename__ = "guardrail_state"
    __table_args__ = (UniqueConstraint("strategy_id", "pair", name="uq_guardrail_state"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String, nullable=False)
    pair = Column(String, nullable=False)
    loss_streak = Column(Integer, nullable=False, default=0)
    pause_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AccountState(Base):
    __tablename__ = "account_state"
    __table_args__ = (UniqueConstraint("strategy_id", name="uq_account_state_strategy"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String, nullable=False)
    equity = Column(Float, nullable=False)
    peak_equity = Column(Float, nullable=False)
    day_start_equity = Column(Float, nullable=False)
    day_start_date = Column(Date, nullable=False)
    consecutive_losses = Column(Integer, nullable=False, default=0)
    halted = Column(Boolean, nullable=False, default=False)
    halt_reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
