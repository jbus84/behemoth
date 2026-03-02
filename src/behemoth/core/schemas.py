from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import ClassVar, Optional

from pydantic import BaseModel, Field


class IncomingTick(BaseModel):
    """Raw tick from cTrader."""
    symbol: str = Field(..., description="The symbol name, e.g., EURUSD")
    timestamp: datetime = Field(..., description="UTC timestamp of the tick")
    bid: float = Field(..., gt=0, description="Bid price")
    ask: float = Field(..., gt=0, description="Ask price")
    tick_volume: float = Field(default=1.0, ge=0, description="Tick volume (usually 1)")


class IncomingTickBar(BaseModel):
    """Aggregated fixed-tick bar (e.g., 100-tick) matching global_tickbars schema."""
    symbol: str = Field(..., description="The symbol name")
    bar_ticks: int = Field(..., gt=0, description="Number of ticks in this bar")
    timestamp: datetime = Field(..., description="Open timestamp (UTC)")
    close_ts: datetime = Field(..., description="Close timestamp (UTC)")
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    spread: float = Field(..., ge=0, description="Spread in absolute price units (e.g., sum or mean during bar)")
    tick_volume: float = Field(..., ge=0, description="Total tick volume during bar")

    # Optional detailed intra-bar structure metrics (often emitted by our build_global_tick_bars.py)
    high_pos_tick: Optional[float] = None
    low_pos_tick: Optional[float] = None
    hl_first: Optional[float] = None
    hl_pos_delta_tick: Optional[float] = None
    hl_pos_frac: Optional[float] = None


class ModelFeatures(BaseModel):
    """The exact 16-parameter feature vector expected by the Stage-03 CatBoost model.

    These must be calculated absolutely identically in pandas (research) and
    the production runtime.  Both paths delegate to the canonical builder in
    ``src.behemoth.core.features.compute_features_from_bars()``.

    Warmup
    ------
    Full-precision computation requires **289 tick bars** in the rolling buffer
    (``cost_window=288`` + 1 for the causal ``.shift(1)``).
    """

    WARMUP_BARS: ClassVar[int] = 289
    """Minimum bars required for full-precision feature computation."""

    cost_est_pips: float = Field(
        ...,
        description=(
            "Estimated round-trip cost in pips. Computed as "
            "rolling-288-bar median spread + 75th-percentile gap slippage proxy, "
            "both lagged by 1 bar for causality."
        ),
    )
    range_pips: float = Field(
        ...,
        description="Bar high-low range in pips. Instantaneous (no rolling window).",
    )
    ret1_pips: float = Field(
        ...,
        description=(
            "1-bar return in pips (close[t] - close[t-1]) / pip_size. "
            "The primary velocity signal."
        ),
    )
    ret_z: float = Field(
        ...,
        description=(
            "Velocity z-score: ret1_pips normalized by rolling-96-bar std of "
            "1-bar returns (lagged 1 bar). Measures how unusual the current "
            "move is relative to recent volatility."
        ),
    )
    ret_abs_z: float = Field(
        ...,
        description=(
            "Absolute velocity z-score: |ret1_pips| / rolling-96-bar std. "
            "Captures magnitude of move regardless of direction."
        ),
    )
    vel_cost_units_h1: float = Field(
        ...,
        description=(
            "1-bar velocity in cost units: ret1_pips / cost_est_pips. "
            "Measures whether the move is large enough to cover transaction costs."
        ),
    )
    vel_abs_cost_units_h1: float = Field(
        ...,
        description=(
            "Absolute 1-bar velocity in cost units: |ret1_pips| / cost_est_pips."
        ),
    )
    spread_z: float = Field(
        ...,
        description=(
            "Spread z-score: current spread normalized by rolling-96-bar mean/std "
            "(lagged 1 bar). Detects unusual spread widening."
        ),
    )
    tick_rate_z: float = Field(
        ...,
        description=(
            "Tick-rate z-score: current ticks/sec normalized by rolling-96-bar "
            "mean/std (lagged 1 bar). Proxy for market activity/liquidity."
        ),
    )
    hour_utc: float = Field(
        ...,
        description="UTC hour of the bar close timestamp (0-23). Session proxy.",
    )
    hl_first: float = Field(
        ...,
        description=(
            "Intra-bar high/low ordering: +1 if high was touched first, "
            "-1 if low first, 0 if simultaneous. Directional microstructure signal."
        ),
    )
    hl_first_mean_24: float = Field(
        ...,
        description=(
            "Rolling 24-bar mean of hl_first (lagged 1 bar). "
            "Captures recent directional microstructure bias."
        ),
    )
    hl_pos_frac_mean_24: float = Field(
        ...,
        description=(
            "Rolling 24-bar mean of hl_pos_frac (lagged 1 bar). "
            "hl_pos_frac = fraction of bar where high preceded low in tick sequence."
        ),
    )
    bar_ticks: float = Field(
        ...,
        description=(
            "Number of ticks per bar (structural parameter, e.g. 100). "
            "Passed through unchanged — not computed from rolling windows."
        ),
    )
    horizon: float = Field(
        ...,
        description=(
            "OCO forward horizon in bars (structural parameter). "
            "Defines how far forward the model looks for barrier touches."
        ),
    )
    barrier_pips: float = Field(
        ...,
        description=(
            "OCO barrier distance in pips (structural parameter). "
            "Defines the stop/limit distance from the entry price."
        ),
    )

    def to_array(self) -> list[float]:
        """Return feature values in schema order (for CatBoost input)."""
        return [getattr(self, k) for k in self.model_fields.keys()]


class OcoPrediction(BaseModel):
    """Strict contract for outputting OCO stop-limit decisions from the models."""
    symbol: str
    close_ts: datetime
    candidate_uid: str = Field(..., description="The exact candidate state identity, e.g. EURUSD_b100_h30_bar... ")
    
    # Model WFO Outputs
    pred_prob: float = Field(..., ge=0.0, le=1.0, description="CatBoost classifier raw probability")
    threshold_exec: float = Field(..., description="The strict rolling execution threshold (q=0.9)")
    selected_exec: int = Field(..., description="1 if pred_prob >= threshold_exec else 0")
    
    # Structural Parameters (for cBot execution)
    horizon: int = Field(..., description="The horizon in bars (e.g. 6)")
    barrier_pips: float = Field(..., description="The OCO barrier distance in pips (e.g. 2.0)")
    cap_pips: float = Field(..., description="The Stop-Limit overshoot cap in pips (e.g. 1.2)")

    # Traceability
    threshold_source: str = Field(..., description="e.g. 'rolling_days' or 'train_fallback'")
    model_month: str = Field(..., description="The YYYY-MM identifier of the model doing the inference")


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TradeOpenRequest(BaseModel):
    """Sent by cBot when a position is opened."""
    symbol: str
    candidate_uid: str
    broker_pos_id: str
    side: str  # Buy / Sell
    entry_price: float
    entry_ts: datetime
    horizon: int


class ActiveTrade(BaseModel):
    """Returned by API for state recovery."""
    broker_pos_id: str
    entry_bar_id: int
    horizon: int


class TradeUpdateRequest(BaseModel):
    """Sent by cBot when a position is closed or cancelled."""
    broker_pos_id: str
    status: TradeStatus
    exit_price: Optional[float] = None
    exit_ts: Optional[datetime] = None
    pnl_pips: Optional[float] = None
