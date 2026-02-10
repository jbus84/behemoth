from datetime import datetime, date
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from .models import PositionStatus, OrderStatus, OrderType, Side, ActiveLeg


class PositionCreate(BaseModel):
    strategy_id: str
    pair: str
    side: Side
    active_leg: ActiveLeg
    size: float
    entry_price: Optional[float] = None
    entry_ts: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PositionOpen(BaseModel):
    entry_price: float
    entry_ts: Optional[datetime] = None


class PositionClose(BaseModel):
    exit_price: float
    exit_ts: Optional[datetime] = None
    pnl_bps: Optional[float] = None


class PositionResponse(BaseModel):
    id: str
    strategy_id: str
    pair: str
    side: Side
    active_leg: ActiveLeg
    status: PositionStatus
    entry_ts: Optional[datetime]
    exit_ts: Optional[datetime]
    entry_price: Optional[float]
    exit_price: Optional[float]
    size: float
    notional_usd: Optional[float] = None
    alloc_frac: Optional[float] = None
    entry_equity: Optional[float] = None
    pnl_bps: Optional[float]
    metadata: Dict[str, Any] = Field(alias="meta")
    version: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OrderCreate(BaseModel):
    position_id: str
    order_type: OrderType = OrderType.MARKET
    qty: float
    price: Optional[float] = None
    slippage_bps: Optional[float] = None


class OrderResponse(BaseModel):
    id: str
    position_id: str
    status: OrderStatus
    order_type: OrderType
    qty: float
    price: Optional[float]
    slippage_bps: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class GuardrailStateResponse(BaseModel):
    strategy_id: str
    pair: str
    loss_streak: int
    pause_until: Optional[datetime]
    can_trade: bool
    cooldown_remaining_s: Optional[int]


class AccountStateResponse(BaseModel):
    strategy_id: str
    equity: float
    peak_equity: float
    day_start_equity: float
    day_start_date: date
    consecutive_losses: int
    halted: bool
    halt_reason: Optional[str]
