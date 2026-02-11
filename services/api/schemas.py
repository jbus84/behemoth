from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import ActiveLeg, OrderStatus, OrderType, PositionStatus, Side


class PositionCreate(BaseModel):
    strategy_id: str
    pair: str
    side: Side
    active_leg: ActiveLeg
    size: float
    entry_price: float | None = None
    entry_ts: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionOpen(BaseModel):
    entry_price: float
    entry_ts: datetime | None = None


class PositionClose(BaseModel):
    exit_price: float
    exit_ts: datetime | None = None
    pnl_bps: float | None = None


class PositionResponse(BaseModel):
    id: str
    strategy_id: str
    pair: str
    side: Side
    active_leg: ActiveLeg
    status: PositionStatus
    entry_ts: datetime | None
    exit_ts: datetime | None
    entry_price: float | None
    exit_price: float | None
    size: float
    notional_usd: float | None = None
    alloc_frac: float | None = None
    entry_equity: float | None = None
    pnl_bps: float | None
    metadata: dict[str, Any] = Field(alias="meta")
    version: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OrderCreate(BaseModel):
    position_id: str
    order_type: OrderType = OrderType.MARKET
    qty: float
    price: float | None = None
    slippage_bps: float | None = None


class OrderResponse(BaseModel):
    id: str
    position_id: str
    status: OrderStatus
    order_type: OrderType
    qty: float
    price: float | None
    slippage_bps: float | None

    model_config = ConfigDict(from_attributes=True)


class GuardrailStateResponse(BaseModel):
    strategy_id: str
    pair: str
    loss_streak: int
    pause_until: datetime | None
    can_trade: bool
    cooldown_remaining_s: int | None


class AccountStateResponse(BaseModel):
    strategy_id: str
    equity: float
    peak_equity: float
    day_start_equity: float
    day_start_date: date
    consecutive_losses: int
    halted: bool
    halt_reason: str | None


class RiskHaltRequest(BaseModel):
    reason: str | None = None
