from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class IncomingTick(BaseModel):
    """Raw tick from cTrader."""
    symbol: str = Field(..., description="The symbol name, e.g., EURUSD")
    timestamp: datetime = Field(..., description="UTC timestamp of the tick")
    bid: float = Field(..., gt=0, description="Bid price")
    ask: float = Field(..., gt=0, description="Ask price")
    tick_volume: float = Field(default=1.0, ge=0, description="Tick volume (usually 1)")
    client_tick_seq: int | None = Field(
        default=None,
        ge=0,
        description="Optional per-symbol monotonic tick sequence from cBot for ingest diagnostics.",
    )
    run_id: str | None = Field(
        default=None,
        description="Optional debug-session identifier emitted by cBot for trace correlation.",
    )


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
    high_pos_tick: float | None = None
    low_pos_tick: float | None = None
    hl_first: float | None = None
    hl_pos_delta_tick: float | None = None
    hl_pos_frac: float | None = None


class ModelFeatures(BaseModel):
    """The exact 16-parameter feature vector expected by the Stage-03 CatBoost model.

    These must be calculated absolutely identically in pandas (research) and
    the production runtime.  Both paths delegate to the canonical builder in
    ``src.behemoth.core.features.compute_features_from_bars()``.

    Rationale for Structural Constraints
    ------------------------------------
    The vector includes 13 continuous market features and 3 structural parameters
    (``bar_ticks``, ``horizon``, ``barrier_pips``). These structural parameters are critical
    meta-learning state constraints. They allow the tree model to correctly partition
    its thresholds based on the exact domain space it is evaluating (e.g., separating logic
    for a 30-pip barrier vs. a 2-pip barrier). Do not remove them to prevent WFO leakage;
    their inclusion is deliberate and structurally necessary.

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
        return [getattr(self, k) for k in type(self).model_fields]


class OcoPrediction(BaseModel):
    """Strict contract for outputting OCO stop-limit decisions from the models."""
    symbol: str
    close_ts: datetime
    candidate_uid: str = Field(..., description="The exact candidate state identity, e.g. EURUSD_b100_h30_bar... ")

    # Model WFO Outputs
    pred_prob: float = Field(..., ge=0.0, le=1.0, description="CatBoost classifier raw probability")
    threshold_exec: float = Field(
        ...,
        description="Execution threshold actually applied to this prediction row",
    )
    selected_exec: int = Field(..., description="1 if pred_prob >= threshold_exec else 0")

    # Structural Parameters (for cBot execution)
    bar_ticks: int = Field(
        default=100,
        description="Tick-bar granularity of the candidate (e.g. 100)",
    )
    horizon: int = Field(..., description="The horizon in bars (e.g. 6)")
    barrier_pips: float = Field(..., description="The OCO barrier distance in pips (e.g. 2.0)")
    cap_pips: float = Field(..., description="The Stop-Limit overshoot cap in pips (e.g. 1.2)")

    # Traceability
    threshold_source: str = Field(
        ...,
        description="Threshold provenance for this row, e.g. 'rolling_days:schedule'",
    )
    model_month: str = Field(..., description="The YYYY-MM identifier of the model doing the inference")
    threshold_blocked: bool = Field(
        default=False,
        description="True when a strict threshold policy (e.g. rolling gap) blocked an otherwise-selected execution row.",
    )
    threshold_block_reason: str | None = Field(
        default=None,
        description="Machine-readable threshold block reason code if threshold_blocked is true.",
    )
    risk_blocked: bool = Field(
        default=False,
        description="True when an account risk guardrail blocked an otherwise-selected execution row.",
    )
    risk_block_reason: str | None = Field(
        default=None,
        description="Machine-readable account risk block reason code if risk_blocked is true.",
    )
    risk_metrics_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Account and cost viability context used during risk evaluation.",
    )
    risk_reserved: bool = Field(
        default=False,
        description="True when the account risk portfolio allocator reserved budget for this row.",
    )
    risk_reserved_amount_ccy: float | None = Field(
        default=None,
        description="Worst-case reserved loss in account currency for this row.",
    )
    risk_headroom_after_ccy: float | None = Field(
        default=None,
        description="Remaining allocator headroom after considering this row.",
    )
    risk_rank_score: float | None = Field(
        default=None,
        description="Allocator ranking score used when budget constraints apply.",
    )
    risk_reservation_id: str | None = Field(
        default=None,
        description="Reservation identifier created by the API allocator for this candidate.",
    )


class BarrierActionType(str, Enum):
    OPEN_MARKET = "OPEN_MARKET"
    CLOSE_MARKET = "CLOSE_MARKET"
    RELEASE_RESERVATION = "RELEASE_RESERVATION"


class BarrierAction(BaseModel):
    """Execution action emitted by the barrier manager."""
    type: BarrierActionType
    symbol: str
    candidate_uid: str
    scan_id: str
    side: str | None = None  # BUY or SELL, present for OPEN_MARKET
    reservation_id: str | None = None  # present for OPEN_MARKET
    broker_pos_id: str | None = None  # present for CLOSE_MARKET


class PredictResponse(BaseModel):
    """Wrapper response for /predict with predictions and barrier actions."""
    predictions: list[OcoPrediction]
    actions: list[BarrierAction] = Field(default_factory=list)


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TradeOpenRequest(BaseModel):
    """Sent by the broker adapter when a position is opened."""
    symbol: str
    candidate_uid: str
    broker_pos_id: str
    side: str  # Buy / Sell
    entry_price: float
    entry_ts: datetime
    horizon: int
    reservation_id: str | None = None
    run_id: str | None = None


class TradeTouchRequest(BaseModel):
    """Sent by the broker adapter when a position's barrier is touched."""
    symbol: str
    broker_pos_id: str
    run_id: str | None = None


class ActiveTrade(BaseModel):
    """Returned by API for state recovery."""
    broker_pos_id: str
    entry_bar_id: int
    horizon: int
    touch_bar_id: int | None = None


class TradeUpdateRequest(BaseModel):
    """Sent by the broker adapter when a position is closed or cancelled."""
    symbol: str
    broker_pos_id: str
    status: TradeStatus
    exit_price: float | None = None
    exit_ts: datetime | None = None
    pnl_pips: float | None = None
    run_id: str | None = None
    close_reason: str | None = None
    commission_ccy: float | None = None


class AccountRiskSnapshotRequest(BaseModel):
    """Periodic account snapshot used for broker-neutral risk enforcement."""
    symbol: str
    balance: float = Field(..., gt=0.0)
    equity: float = Field(..., gt=0.0)
    snapshot_ts: datetime | None = None
    run_id: str | None = None


