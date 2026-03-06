"""FastAPI inference server for the OCO stop-limit strategy.

Endpoints:
    POST /bars         – Ingest a new tick bar from cTrader
    POST /predict      – Compute features and run CatBoost inference
    GET  /health       – Model validity, buffer depth, and system status
    GET  /status       – Per-symbol state summary (bar counts, last timestamps)

Model loading:
    On startup (or hot-reload via POST /reload), the server loads the
    CatBoost ``.cbm`` binary and paired threshold JSON pinned in the
    governance lock for each symbol.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from src.behemoth.api.dashboard import router as dashboard_router
from src.behemoth.core.registry import CandidateRegistry
from src.behemoth.core.schemas import (
    ActiveTrade,
    FtmoAccountSnapshotRequest,
    IncomingTick,
    IncomingTickBar,
    ModelFeatures,
    OcoPrediction,
    TradeOpenRequest,
    TradeTouchRequest,
    TradeUpdateRequest,
)
from src.behemoth.risk.ftmo import (
    FtmoProfile,
    evaluate_account_limits,
    evaluate_trade_guard,
    load_ftmo_profile,
    trading_day_id,
)
from src.behemoth.runtime.state import StateManager
from src.behemoth.runtime.tick_aggregator import TickAggregator

logger = logging.getLogger("behemoth.api")

# ── App ───────────────────────────────────────────────────────────────

# ── Global State ──────────────────────────────────────────────────────

_state: StateManager | None = None
_aggregators: dict[int, TickAggregator] = {}
_registry: CandidateRegistry | None = None
_models: dict[str, object] = {}          # symbol -> loaded CatBoostClassifier
_thresholds: dict[str, dict] = {}        # symbol -> threshold config
_model_months: dict[str, str] = {}       # symbol -> "2025-12"
_models_dir: Path = Path("models/oco")
_ftmo_rules_path: Path = Path("configs/research/governance/ftmo/ftmo_rules.yaml")
_ftmo_profile: FtmoProfile | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# ── Prometheus Metrics ────────────────────────────────────────────────
METRIC_INFERENCE_LATENCY = Histogram(
    "behemoth_inference_latency_seconds",
    "Time spent in CatBoost inference",
    ["symbol"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

METRIC_TRADES_TOTAL = Counter(
    "behemoth_trades_total",
    "Total trade intents",
    ["symbol", "status"]  # status: OPEN, FILLED, REJECTED, CLOSED, CANCELLED
)

METRIC_SLIPPAGE_PIPS = Histogram(
    "behemoth_slippage_pips",
    "Realized vs Expected entry slippage",
    ["symbol"],
    buckets=(-0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5, 1.0, 2.0)
)

METRIC_EQUITY_PIPS = Gauge(
    "behemoth_equity_pips",
    "Cumulative realized PnL in pips",
    ["symbol"]
)

METRIC_BAR_COUNT = Gauge(
    "behemoth_bar_count",
    "Current bar count in state manager",
    ["symbol"]
)

METRIC_RISK_BLOCKS_TOTAL = Counter(
    "behemoth_risk_blocks_total",
    "Total FTMO/risk blocked execution intents",
    ["symbol", "reason"],
)

METRIC_FTMO_DAILY_HEADROOM = Gauge(
    "behemoth_ftmo_daily_loss_headroom",
    "Remaining buffered daily loss headroom in account currency units",
    ["symbol"],
)

METRIC_FTMO_MAX_HEADROOM = Gauge(
    "behemoth_ftmo_max_loss_headroom",
    "Remaining buffered max loss headroom in account currency units",
    ["symbol"],
)

METRIC_FTMO_RESERVED_LOSS_CCY = Gauge(
    "behemoth_ftmo_reserved_loss_ccy",
    "Active reserved FTMO worst-case loss budget in account currency",
    ["symbol"],
)

METRIC_FTMO_ALLOCATOR_BLOCKS_TOTAL = Counter(
    "behemoth_ftmo_allocator_blocks_total",
    "Total FTMO allocator budget blocks",
    ["symbol", "reason"],
)

METRIC_FTMO_ALLOCATOR_ADMITTED_TOTAL = Counter(
    "behemoth_ftmo_allocator_admitted_total",
    "Total FTMO allocator-admitted candidates",
    ["symbol"],
)


class AppConfig(BaseModel):
    """Runtime configuration for the inference server."""
    vol_window: int = 96
    cost_window: int = 288
    models_dir: str = Field(default_factory=lambda: os.getenv("BEHEMOTH_MODELS_DIR", "models/oco"))
    registry_path: str = Field(default_factory=lambda: os.getenv("BEHEMOTH_REGISTRY_PATH", "configs/research/governance/oco_rule_universe_registry.yaml"))
    symbols: list[str] = Field(
        default=["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    )
    persist_db_path: str | None = Field(
        default_factory=lambda: os.getenv("BEHEMOTH_STATE_DB", "data/db/behemoth_runtime.db")
    )
    ftmo_enabled: bool = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_FTMO_ENABLED", "true")).strip().lower()
        in {"1", "true", "yes", "y"}
    )
    ftmo_enforce_blocks: bool = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_FTMO_ENFORCE_BLOCKS", "true")).strip().lower()
        in {"1", "true", "yes", "y"}
    )
    ftmo_rules_path: str = Field(
        default_factory=lambda: os.getenv(
            "BEHEMOTH_FTMO_RULES_PATH",
            "configs/research/governance/ftmo/ftmo_rules.yaml",
        )
    )
    ftmo_profile_id: str = Field(
        default_factory=lambda: os.getenv(
            "BEHEMOTH_FTMO_PROFILE_ID",
            "ftmo_10k_challenge_2step",
        )
    )
    ftmo_pending_reservation_ttl_sec: int = Field(
        default_factory=lambda: int(os.getenv("BEHEMOTH_FTMO_PENDING_RESERVATION_TTL_SEC", "1800"))
    )


_config = AppConfig()


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event."""
    global _state, _aggregators, _registry, _models_dir, _ftmo_rules_path, _ftmo_profile

    # Start background monitor
    monitor_task = asyncio.create_task(_monitor_ledger())

    if _config.persist_db_path:
        db_path = Path(_config.persist_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Using persistent State DB: %s", db_path)
        _state = StateManager(
            vol_window=_config.vol_window,
            cost_window=_config.cost_window,
            persist_path=str(db_path),
        )
    else:
        _state = StateManager(
            vol_window=_config.vol_window,
            cost_window=_config.cost_window,
        )
    try:
        _registry = CandidateRegistry.load(os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"))
        logger.info("Loaded %d candidates from governance locks", len(_registry.all_candidates()))

        unique_bar_ticks = {int(c.bar_ticks) for c in _registry.all_candidates()}
        for bt in unique_bar_ticks:
            _aggregators[bt] = TickAggregator(bar_ticks=bt)
            logger.info("Initialized TickAggregator for %d ticks", bt)

    except FileNotFoundError:
        _registry = None
        _aggregators[100] = TickAggregator(bar_ticks=100) # Fallback
        logger.warning("Governance lock dir not found — using empty registry and default 100-tick aggregator")
    _models_dir = Path(_config.models_dir)
    _load_models()
    _ftmo_rules_path = Path(_config.ftmo_rules_path)
    _ftmo_profile = None
    if _config.ftmo_enabled:
        try:
            _ftmo_profile = load_ftmo_profile(
                _ftmo_rules_path,
                _config.ftmo_profile_id,
            )
            logger.info(
                "Loaded FTMO profile %s from %s",
                _ftmo_profile.profile_id,
                _ftmo_rules_path,
            )
        except Exception as exc:
            logger.error("Failed to load FTMO rules: %s", exc)
    logger.info("Behemoth API started. Models dir: %s", _models_dir)
    yield
    monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task

    if _state:
        _state.close()
        _state = None


async def _monitor_ledger() -> None:
    """Background task to sync DuckDB stats to Prometheus."""
    while True:
        try:
            if _state:
                # Update bar counts (using 100-ticks as standard tracking metric)
                for sym in _state.get_all_symbols():
                    METRIC_BAR_COUNT.labels(symbol=sym).set(_state.bar_count(sym, 100))

                # Update ledger stats (PnL, Win Rate)
                stats = _state.get_ledger_stats()
                for s in stats:
                    METRIC_EQUITY_PIPS.labels(symbol=s["symbol"]).set(s["total_pnl"])
                    # We could add a win_rate gauge here if needed
                if _config.ftmo_enabled and (_ftmo_profile is not None):
                    include_pending = bool(_ftmo_profile.allocator.allocator_reserve_pending)
                    include_open = bool(_ftmo_profile.allocator.allocator_reserve_open)
                    for sym in _config.symbols:
                        reserved = _state.sum_active_ftmo_reserved_loss_ccy(
                            symbol=sym,
                            include_pending=include_pending,
                            include_open=include_open,
                        )
                        METRIC_FTMO_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(reserved))
        except Exception as e:
            logger.error("Ledger monitor error: %s", e)
        await asyncio.sleep(60)


app = FastAPI(
    title="Behemoth OCO Inference API",
    version="0.1.0",
    description="Production inference server for the tick-based OCO stop-limit strategy.",
    lifespan=lifespan,
)

app.include_router(dashboard_router)


def _load_models() -> None:
    """Load governance-pinned model artifacts per symbol."""
    global _models, _thresholds, _model_months
    _models = {}
    _thresholds = {}
    _model_months = {}
    if not _models_dir.exists():
        logger.warning("Models directory %s does not exist yet.", _models_dir)
        return

    try:
        from catboost import CatBoostClassifier
    except ImportError:
        logger.error("CatBoost not installed — predictions will be unavailable.")
        return

    if _registry is None:
        logger.error("Governance registry unavailable — refusing to load models without lock binding.")
        return

    for sym in _config.symbols:
        binding = _registry.get_model_binding(sym)
        if not binding:
            logger.error("No governance model binding for %s — skipping model load.", sym)
            continue
        model_path = Path(str(binding.get("model_cbm_path", "")))
        thr_path = Path(str(binding.get("model_threshold_json_path", "")))
        exp_model_sha = str(binding.get("model_cbm_sha256", "")).strip()
        exp_thr_sha = str(binding.get("model_threshold_json_sha256", "")).strip()
        lock_month = str(binding.get("model_month", "")).strip()
        if (not model_path.exists()) or (not thr_path.exists()):
            logger.error(
                "Locked artifacts missing for %s: model=%s threshold=%s",
                sym,
                model_path,
                thr_path,
            )
            continue
        got_model_sha = _sha256(model_path)
        got_thr_sha = _sha256(thr_path)
        if (got_model_sha != exp_model_sha) or (got_thr_sha != exp_thr_sha):
            logger.error("Locked artifact hash mismatch for %s — refusing model load.", sym)
            continue
        month = model_path.stem.split("_")[-1]
        if lock_month and (month != lock_month):
            logger.error(
                "Locked model month mismatch for %s: lock=%s file=%s",
                sym,
                lock_month,
                month,
            )
            continue

        model = CatBoostClassifier()
        model.load_model(str(model_path))
        _models[sym] = model
        _model_months[sym] = month
        logger.info("Loaded lock-bound model for %s (month %s): %s", sym, month, model_path.name)

        # Load paired threshold JSON
        _thresholds[sym] = json.loads(thr_path.read_text())
        logger.info("Loaded threshold config for %s", sym)

def _get_cap_pips(symbol: str) -> float:
    """Get production Stop-Limit cap for a symbol from governance registry."""
    if _registry is None:
        return 1.2
    return _registry.get_cap_pips(symbol)


def _pip_size_for_symbol(sym: str) -> float:
    return 0.01 if sym.upper().endswith("JPY") else 0.0001


def _default_price_for_symbol(sym: str) -> float:
    defaults = {
        "USDJPY": 150.0,
        "USDCHF": 0.90,
        "USDCAD": 1.35,
        "EURUSD": 1.08,
        "GBPUSD": 1.27,
        "AUDUSD": 0.66,
    }
    return float(defaults.get(sym.upper(), 1.0))


def _latest_price_for_symbol(sym: str) -> float:
    if _state is None:
        return _default_price_for_symbol(sym)
    row = _state._con.execute(
        """
        SELECT close_price
        FROM tick_bars
        WHERE symbol = ?
        ORDER BY row_id DESC
        LIMIT 1
        """,
        [sym.upper()],
    ).fetchone()
    if row and row[0] is not None:
        return float(row[0])
    return _default_price_for_symbol(sym)


def _pip_value_per_unit_ccy(sym: str, *, price: float) -> float | None:
    s = sym.upper()
    pip = _pip_size_for_symbol(s)
    if s.endswith("USD"):
        return pip
    if s.startswith("USD"):
        p = max(float(price), 1e-9)
        return pip / p
    return None


def _resolve_requested_volume_units(req: PredictRequest) -> float:
    if req.requested_volume_units is not None:
        v = float(req.requested_volume_units)
        if v <= 0:
            raise HTTPException(status_code=422, detail="requested_volume_units must be > 0")
        return v
    if req.requested_lot_size is not None:
        lot = float(req.requested_lot_size)
        if lot <= 0:
            raise HTTPException(status_code=422, detail="requested_lot_size must be > 0")
        return lot * 100000.0
    raise HTTPException(
        status_code=422,
        detail="One of requested_volume_units or requested_lot_size is required",
    )


@dataclass
class _CandidateDecision:
    candidate_uid: str
    cand: Any
    features: ModelFeatures
    pred_prob: float
    curr_threshold: float
    curr_source: str
    preselected_exec: int
    selected_exec: int
    risk_blocked: bool
    risk_block_reason: str | None
    risk_metrics_snapshot: dict[str, Any]
    trade_eval: dict[str, Any]
    risk_rank_score: float | None = None
    risk_reserved: bool = False
    risk_reserved_amount_ccy: float | None = None
    risk_headroom_after_ccy: float | None = None
    risk_reservation_id: str | None = None


def _resolve_ftmo_account_eval(sym: str, now_utc: datetime) -> dict[str, Any]:
    if (not _config.ftmo_enabled) or (_ftmo_profile is None) or (_state is None):
        return {
            "enabled": False,
            "profile_id": None,
            "allow_trading": True,
            "block_reason": None,
            "snapshot_available": False,
            "trading_day_id": None,
        }

    prof = _ftmo_profile
    latest = _state.get_latest_ftmo_account_snapshot(sym)
    if latest is None:
        latest = _state.get_latest_ftmo_account_snapshot(None)

    if latest is None:
        eval_out = evaluate_account_limits(
            prof,
            balance=None,
            equity=None,
            day_start_balance=None,
        )
        eval_out["enabled"] = True
        eval_out["profile_id"] = prof.profile_id
        eval_out["trading_day_id"] = trading_day_id(
            now_utc,
            timezone_name=prof.daily_reset_timezone,
            reset_hour=prof.daily_reset_hour,
            reset_minute=prof.daily_reset_minute,
        )
        return eval_out

    since = now_utc
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    else:
        since = since.astimezone(timezone.utc)
    since = since - timedelta(days=3)

    snaps = _state.get_ftmo_snapshots_since(since_ts=since, symbol=sym)
    if not snaps:
        snaps = _state.get_ftmo_snapshots_since(since_ts=since, symbol=None)

    day_id = trading_day_id(
        now_utc,
        timezone_name=prof.daily_reset_timezone,
        reset_hour=prof.daily_reset_hour,
        reset_minute=prof.daily_reset_minute,
    )
    day_start_balance: float | None = None
    for row in snaps:
        row_day = trading_day_id(
            row["snapshot_ts"],
            timezone_name=prof.daily_reset_timezone,
            reset_hour=prof.daily_reset_hour,
            reset_minute=prof.daily_reset_minute,
        )
        if row_day == day_id:
            day_start_balance = float(row["balance"])
            break
    if day_start_balance is None:
        day_start_balance = float(latest["balance"])

    eval_out = evaluate_account_limits(
        prof,
        balance=float(latest["balance"]),
        equity=float(latest["equity"]),
        day_start_balance=day_start_balance,
    )
    eval_out["enabled"] = True
    eval_out["profile_id"] = prof.profile_id
    eval_out["trading_day_id"] = day_id

    daily_headroom = eval_out.get("daily_loss_headroom")
    max_headroom = eval_out.get("max_loss_headroom")
    if daily_headroom is not None:
        METRIC_FTMO_DAILY_HEADROOM.labels(symbol=sym).set(float(daily_headroom))
    if max_headroom is not None:
        METRIC_FTMO_MAX_HEADROOM.labels(symbol=sym).set(float(max_headroom))
    return eval_out


def _ftmo_limits_payload() -> FtmoLimitsResponse:
    if (not _config.ftmo_enabled) or (_ftmo_profile is None):
        return FtmoLimitsResponse(enabled=False)
    prof = _ftmo_profile
    return FtmoLimitsResponse(
        enabled=True,
        profile_id=prof.profile_id,
        mode=prof.mode,
        currency=prof.currency,
        initial_balance=prof.initial_balance,
        daily_loss_limit_hard=prof.daily_loss_limit,
        max_loss_limit_hard=prof.max_loss_limit,
        daily_loss_limit_internal=prof.daily_loss_limit * (1.0 - prof.buffers.daily_loss_buffer_pct),
        max_loss_limit_internal=prof.max_loss_limit * (1.0 - prof.buffers.max_loss_buffer_pct),
        daily_reset_timezone=prof.daily_reset_timezone,
        daily_reset_hour=prof.daily_reset_hour,
        daily_reset_minute=prof.daily_reset_minute,
        profit_target_phase1=prof.profit_target_phase1,
        profit_target_phase2=prof.profit_target_phase2,
        min_trading_days=prof.min_trading_days,
        cost_gate={
            "commission_round_turn_pips": prof.cost_gate.commission_round_turn_pips,
            "slippage_floor_pips": prof.cost_gate.slippage_floor_pips,
            "min_edge_buffer_pips": prof.cost_gate.min_edge_buffer_pips,
            "max_cost_to_barrier_ratio": prof.cost_gate.max_cost_to_barrier_ratio,
            "require_account_snapshot": prof.cost_gate.require_account_snapshot,
        },
        allocator={
            "allocator_enabled": prof.allocator.allocator_enabled,
            "allocator_budget_fraction_daily": prof.allocator.allocator_budget_fraction_daily,
            "allocator_budget_fraction_max": prof.allocator.allocator_budget_fraction_max,
            "allocator_min_headroom_buffer_ccy": prof.allocator.allocator_min_headroom_buffer_ccy,
            "allocator_reserve_pending": prof.allocator.allocator_reserve_pending,
            "allocator_reserve_open": prof.allocator.allocator_reserve_open,
            "allocator_priority": prof.allocator.allocator_priority,
        },
        official_source_url=prof.official_source_url,
    )


# ── Request / Response Models ─────────────────────────────────────────

class PredictRequest(BaseModel):
    """Prediction request with explicit intended size for FTMO allocation."""
    symbol: str
    requested_volume_units: float | None = Field(
        default=None,
        gt=0.0,
        description="Intended execution size in broker volume units.",
    )
    requested_lot_size: float | None = Field(
        default=None,
        gt=0.0,
        description="Optional intended lot size (converted to units using 100k FX lot).",
    )


class HealthResponse(BaseModel):
    status: str
    utc_now: datetime
    models_loaded: dict[str, str]
    bar_counts: dict[str, int]


class StatusSymbol(BaseModel):
    symbol: str
    bar_count: int
    model_loaded: bool
    model_month: str | None = None
    has_threshold: bool


class BackfillRequest(BaseModel):
    """Batch of raw ticks for instant warmup."""
    symbol: str
    bar_ticks: int = 100
    ticks: list[IncomingTick]


class FtmoLimitsResponse(BaseModel):
    enabled: bool
    profile_id: str | None = None
    mode: str | None = None
    currency: str | None = None
    initial_balance: float | None = None
    daily_loss_limit_hard: float | None = None
    max_loss_limit_hard: float | None = None
    daily_loss_limit_internal: float | None = None
    max_loss_limit_internal: float | None = None
    daily_reset_timezone: str | None = None
    daily_reset_hour: int | None = None
    daily_reset_minute: int | None = None
    profit_target_phase1: float | None = None
    profit_target_phase2: float | None = None
    min_trading_days: int | None = None
    cost_gate: dict[str, Any] = Field(default_factory=dict)
    allocator: dict[str, Any] = Field(default_factory=dict)
    official_source_url: str | None = None


class FtmoStatusResponse(BaseModel):
    enabled: bool
    symbol: str | None = None
    profile_id: str | None = None
    as_of_utc: datetime
    trading_day_id: str | None = None
    allow_trading: bool = True
    block_reason: str | None = None
    snapshot_available: bool = False
    balance: float | None = None
    equity: float | None = None
    day_start_balance: float | None = None
    daily_loss_used: float | None = None
    max_loss_used: float | None = None
    daily_loss_headroom: float | None = None
    max_loss_headroom: float | None = None


class FtmoReservationReleaseRequest(BaseModel):
    symbol: str | None = None
    candidate_uid: str | None = None
    broker_pos_id: str | None = None
    reservation_id: str | None = None
    reason: str | None = None


class FtmoReservationsStatusResponse(BaseModel):
    enabled: bool
    symbol: str | None = None
    active_count: int = 0
    total_reserved_loss_ccy: float = 0.0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    include_pending: bool = True
    include_open: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────

@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/risk/ftmo/snapshot", status_code=201)
async def ingest_ftmo_snapshot(req: FtmoAccountSnapshotRequest) -> dict[str, Any]:
    """Ingest account balance/equity snapshots emitted by cBot."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ts = req.snapshot_ts or datetime.now(tz=timezone.utc)
    _state.record_ftmo_account_snapshot(
        symbol=req.symbol,
        balance=float(req.balance),
        equity=float(req.equity),
        snapshot_ts=ts,
    )
    return {
        "ok": True,
        "symbol": req.symbol.upper(),
        "snapshot_ts": ts,
    }


@app.get("/risk/ftmo/limits", response_model=FtmoLimitsResponse)
async def get_ftmo_limits() -> FtmoLimitsResponse:
    """Return active FTMO profile limits and internal buffered thresholds."""
    return _ftmo_limits_payload()


@app.get("/risk/ftmo/status", response_model=FtmoStatusResponse)
async def get_ftmo_status(symbol: str | None = None) -> FtmoStatusResponse:
    """Return current FTMO guardrail status and account headroom."""
    sym = str(symbol or "").strip().upper() or None
    now_utc = datetime.now(tz=timezone.utc)
    eval_out = _resolve_ftmo_account_eval(sym or "ALL", now_utc)
    return FtmoStatusResponse(
        enabled=bool(eval_out.get("enabled", False)),
        symbol=sym,
        profile_id=eval_out.get("profile_id"),
        as_of_utc=now_utc,
        trading_day_id=eval_out.get("trading_day_id"),
        allow_trading=bool(eval_out.get("allow_trading", True)),
        block_reason=eval_out.get("block_reason"),
        snapshot_available=bool(eval_out.get("snapshot_available", False)),
        balance=eval_out.get("balance"),
        equity=eval_out.get("equity"),
        day_start_balance=eval_out.get("day_start_balance"),
        daily_loss_used=eval_out.get("daily_loss_used"),
        max_loss_used=eval_out.get("max_loss_used"),
        daily_loss_headroom=eval_out.get("daily_loss_headroom"),
        max_loss_headroom=eval_out.get("max_loss_headroom"),
    )


@app.get("/risk/ftmo/reservations/status", response_model=FtmoReservationsStatusResponse)
async def get_ftmo_reservations_status(symbol: str | None = None) -> FtmoReservationsStatusResponse:
    """Return active FTMO reservation totals and rows."""
    sym = str(symbol or "").strip().upper() or None
    if (not _config.ftmo_enabled) or (_ftmo_profile is None) or (_state is None):
        return FtmoReservationsStatusResponse(enabled=False, symbol=sym)
    include_pending = bool(_ftmo_profile.allocator.allocator_reserve_pending)
    include_open = bool(_ftmo_profile.allocator.allocator_reserve_open)
    total_reserved = _state.sum_active_ftmo_reserved_loss_ccy(
        symbol=sym,
        include_pending=include_pending,
        include_open=include_open,
    )
    rows = _state.list_active_ftmo_risk_reservations(symbol=sym)
    return FtmoReservationsStatusResponse(
        enabled=True,
        symbol=sym,
        active_count=len(rows),
        total_reserved_loss_ccy=float(total_reserved),
        rows=rows,
        include_pending=include_pending,
        include_open=include_open,
    )


@app.post("/risk/ftmo/reservations/release")
async def release_ftmo_reservations(req: FtmoReservationReleaseRequest) -> dict[str, Any]:
    """Release active FTMO reservations by reservation id, candidate uid, or broker pos id."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    if not any([req.reservation_id, req.candidate_uid, req.broker_pos_id]):
        raise HTTPException(
            status_code=422,
            detail="One of reservation_id, candidate_uid, or broker_pos_id is required",
        )
    released = _state.release_ftmo_risk_reservation(
        reservation_id=req.reservation_id,
        candidate_uid=req.candidate_uid,
        broker_pos_id=req.broker_pos_id,
        symbol=req.symbol,
        reason=req.reason or "manual_release",
    )
    return {"ok": True, "released_count": int(released)}


@app.post("/bars", status_code=201)
async def ingest_bar(bar: IncomingTickBar) -> dict:
    """Ingest a new tick bar into the state buffer."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    _state.append_bar(bar)
    return {
        "ok": True,
        "symbol": bar.symbol,
        "bar_count": _state.bar_count(bar.symbol, bar.bar_ticks),
    }


@app.post("/predict", response_model=list[OcoPrediction])
async def predict(req: PredictRequest) -> list[OcoPrediction]:
    """Evaluate all registry candidates for a symbol and return predictions.

    Computes rolling features once, then runs CatBoost inference for each
    candidate (different horizon/barrier_pips). Returns results sorted by
    pred_prob descending.
    """
    sym = req.symbol.upper()
    requested_volume_units = _resolve_requested_volume_units(req)

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    # Get candidates from registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Candidate registry not loaded")

    candidates = _registry.get_candidates(sym)
    if not candidates:
        raise HTTPException(status_code=422, detail=f"No candidates registered for {sym}")

    _check_warmup(sym, candidates)

    # Load model
    model = _models.get(sym)
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"No CatBoost model loaded for {sym}. "
                   f"Export models via run_tick_opportunity_monthly_wfo.py first.",
        )

    # Compute base rolling features per bar_ticks group
    base_features_by_ticks: dict[int, ModelFeatures] = {}

    for cand in candidates:
        bt = int(cand.bar_ticks)
        if bt not in base_features_by_ticks:
            feats = _state.compute_features(
                symbol=sym,
                bar_ticks=bt,
                horizon=cand.horizon,
                barrier_pips=cand.barrier_pips,
            )
            if feats is None:
                raise HTTPException(status_code=422, detail=f"Feature computation failed for {sym}")
            base_features_by_ticks[bt] = feats


    thr_cfg = _thresholds.get(sym, {})
    float(thr_cfg.get("threshold_exec", 0.5))
    str(thr_cfg.get("threshold_source", "default"))
    _model_months.get(sym, "unknown")

    # In live trading this is functionally current time, but in replay we must
    # exactly align with the state DB's reconstructed chronological limit.
    close_ts = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
    ftmo_account_eval = _resolve_ftmo_account_eval(sym, close_ts)
    _state.expire_stale_ftmo_pending_reservations(
        max_age_seconds=max(60, int(_config.ftmo_pending_reservation_ttl_sec)),
    )

    results = _build_predictions(
        sym=sym,
        candidates=candidates,
        model=model,
        base_features_by_ticks=base_features_by_ticks,
        close_ts=close_ts,
        thr_cfg=thr_cfg,
        ftmo_account_eval=ftmo_account_eval,
        requested_volume_units=requested_volume_units,
    )

    # Sort by pred_prob descending
    results.sort(key=lambda p: p.pred_prob, reverse=True)
    return results


def _check_warmup(sym: str, candidates: list[Any]) -> None:
    """Validate sufficient bars exist for the requested candidates."""
    if _state is None:
        return
    warmup_needed = max(_config.vol_window, _config.cost_window) + 1
    for cand in candidates:
        bar_count = _state.bar_count(sym, cand.bar_ticks)
        if bar_count < warmup_needed:
            raise HTTPException(
                status_code=422,
                detail=f"Insufficient warmup bars for {sym} at {cand.bar_ticks} ticks. "
                f"Have {bar_count}, need ≥{warmup_needed}.",
            )


def _build_predictions(
    sym: str,
    candidates: list[Any],
    model: Any,
    base_features_by_ticks: dict[int, ModelFeatures],
    close_ts: datetime,
    thr_cfg: dict[str, Any],
    ftmo_account_eval: dict[str, Any],
    requested_volume_units: float,
) -> list[OcoPrediction]:
    """Build predictions for each candidate using model + FTMO portfolio allocator."""
    import numpy as np

    threshold_exec = float(thr_cfg.get("threshold_exec", 0.5))
    threshold_mode = str(thr_cfg.get("threshold_source", "default"))
    model_month = _model_months.get(sym, "unknown")
    logger.debug(
        "Predict %s: threshold_exec=%.4f mode=%s month=%s",
        sym, threshold_exec, threshold_mode, model_month,
    )

    decisions: list[_CandidateDecision] = []
    price_now = _latest_price_for_symbol(sym)
    pip_value_per_unit = _pip_value_per_unit_ccy(sym, price=price_now)

    if _config.ftmo_enabled and (_ftmo_profile is not None) and pip_value_per_unit is None:
        pip_value_per_unit = 0.0

    for cand in candidates:
        base_features = base_features_by_ticks[int(cand.bar_ticks)]
        features = base_features.model_copy(
            update={
                "bar_ticks": float(cand.bar_ticks),
                "horizon": float(cand.horizon),
                "barrier_pips": float(cand.barrier_pips),
            }
        )
        arr = np.array([features.to_array()], dtype=float)

        if model is not None:
            with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
                pred_prob = float(model.predict_proba(arr)[:, 1][0])
        else:
            pred_prob = 0.0

        # Dynamic threshold lookup. If the model export includes a per-day
        # schedule, use it; otherwise, fall back to the static scalar.
        schedule = thr_cfg.get("threshold_schedule", {})
        day_str = close_ts.strftime("%Y-%m-%d")

        if schedule and day_str in schedule:
            curr_threshold = float(schedule[day_str])
            curr_source = f"{threshold_mode}:schedule"
        else:
            curr_threshold = threshold_exec
            curr_source = f"{threshold_mode}:static_fallback"

        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        preselected_exec = 1 if pred_prob >= curr_threshold else 0
        risk_metrics_snapshot: dict[str, Any] = {
            "ftmo_enabled": bool(ftmo_account_eval.get("enabled", False)),
            "ftmo_profile_id": ftmo_account_eval.get("profile_id"),
            "ftmo_allow_trading": bool(ftmo_account_eval.get("allow_trading", True)),
            "ftmo_account_block_reason": ftmo_account_eval.get("block_reason"),
            "snapshot_available": bool(ftmo_account_eval.get("snapshot_available", False)),
            "daily_loss_headroom": ftmo_account_eval.get("daily_loss_headroom"),
            "max_loss_headroom": ftmo_account_eval.get("max_loss_headroom"),
            "daily_loss_used": ftmo_account_eval.get("daily_loss_used"),
            "max_loss_used": ftmo_account_eval.get("max_loss_used"),
            "trading_day_id": ftmo_account_eval.get("trading_day_id"),
            "requested_volume_units": float(requested_volume_units),
        }
        trade_eval: dict[str, Any] = {"allow_trade": True, "block_reason": None}
        selected_exec = preselected_exec
        risk_blocked = False
        risk_block_reason: str | None = None

        if preselected_exec == 1 and _config.ftmo_enabled and (_ftmo_profile is not None):
            trade_eval = evaluate_trade_guard(
                _ftmo_profile,
                account_eval=ftmo_account_eval,
                pred_prob=pred_prob,
                threshold_exec=curr_threshold,
                barrier_pips=float(cand.barrier_pips),
                cost_est_pips=float(features.cost_est_pips),
            )
            risk_metrics_snapshot.update(trade_eval)
            if _config.ftmo_enforce_blocks and (not bool(trade_eval.get("allow_trade", True))):
                selected_exec = 0
                risk_blocked = True
                risk_block_reason = str(trade_eval.get("block_reason") or "FTMO_BLOCKED")
                METRIC_RISK_BLOCKS_TOTAL.labels(symbol=sym, reason=risk_block_reason).inc()

        rank_score = None
        if preselected_exec == 1:
            expected_edge = trade_eval.get("expected_edge_proxy_pips")
            est_cost = trade_eval.get("estimated_trade_cost_pips")
            if expected_edge is not None and est_cost is not None:
                rank_score = float(expected_edge) - float(est_cost)
            else:
                rank_score = float(pred_prob) - float(curr_threshold)

        decisions.append(
            _CandidateDecision(
                candidate_uid=canonical_uid,
                cand=cand,
                features=features,
                pred_prob=float(pred_prob),
                curr_threshold=float(curr_threshold),
                curr_source=curr_source,
                preselected_exec=preselected_exec,
                selected_exec=selected_exec,
                risk_blocked=risk_blocked,
                risk_block_reason=risk_block_reason,
                risk_metrics_snapshot=risk_metrics_snapshot,
                trade_eval=trade_eval,
                risk_rank_score=rank_score,
            )
        )

    allocator_enabled = bool(
        _config.ftmo_enabled
        and _ftmo_profile is not None
        and _ftmo_profile.allocator.allocator_enabled
        and _state is not None
        and _config.ftmo_enforce_blocks
    )

    if allocator_enabled:
        include_pending = bool(_ftmo_profile.allocator.allocator_reserve_pending)
        include_open = bool(_ftmo_profile.allocator.allocator_reserve_open)
        active_reserved_loss_ccy = _state.sum_active_ftmo_reserved_loss_ccy(
            include_pending=include_pending,
            include_open=include_open,
        )
        daily_headroom = ftmo_account_eval.get("daily_loss_headroom")
        max_headroom = ftmo_account_eval.get("max_loss_headroom")
        daily_budget = None if daily_headroom is None else float(daily_headroom) * float(_ftmo_profile.allocator.allocator_budget_fraction_daily)
        max_budget = None if max_headroom is None else float(max_headroom) * float(_ftmo_profile.allocator.allocator_budget_fraction_max)
        if daily_budget is None and max_budget is None:
            allocator_remaining = 0.0
        elif daily_budget is None:
            allocator_remaining = float(max_budget)
        elif max_budget is None:
            allocator_remaining = float(daily_budget)
        else:
            allocator_remaining = min(float(daily_budget), float(max_budget))
        allocator_remaining = (
            allocator_remaining
            - float(_ftmo_profile.allocator.allocator_min_headroom_buffer_ccy)
            - float(active_reserved_loss_ccy)
        )
        allocator_remaining = max(0.0, allocator_remaining)
        METRIC_FTMO_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(active_reserved_loss_ccy))

        to_allocate = [
            d
            for d in decisions
            if d.preselected_exec == 1 and d.selected_exec == 1
        ]
        to_allocate.sort(
            key=lambda d: (
                float(d.risk_rank_score if d.risk_rank_score is not None else -1e12),
                float(d.pred_prob),
            ),
            reverse=True,
        )
        newly_reserved_ccy = 0.0
        for d in to_allocate:
            est_cost = d.trade_eval.get("estimated_trade_cost_pips")
            if est_cost is None:
                continue
            if pip_value_per_unit is None or pip_value_per_unit <= 0:
                d.selected_exec = 0
                d.risk_blocked = True
                d.risk_block_reason = "FTMO_PIP_VALUE_UNAVAILABLE"
                d.risk_metrics_snapshot["allocator_remaining_before_ccy"] = float(allocator_remaining)
                METRIC_RISK_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                METRIC_FTMO_ALLOCATOR_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                continue

            gross_loss_pips = max(
                0.0,
                float(d.cand.barrier_pips) + float(_get_cap_pips(sym)) + float(est_cost),
            )
            reserve_ccy = float(gross_loss_pips) * float(pip_value_per_unit) * float(requested_volume_units)
            d.risk_metrics_snapshot["allocator_gross_loss_pips"] = float(gross_loss_pips)
            d.risk_metrics_snapshot["allocator_reserved_loss_ccy"] = float(reserve_ccy)
            d.risk_metrics_snapshot["allocator_remaining_before_ccy"] = float(allocator_remaining)
            if reserve_ccy <= allocator_remaining:
                allocator_remaining -= reserve_ccy
                newly_reserved_ccy += reserve_ccy
                d.risk_reserved = True
                d.risk_reserved_amount_ccy = float(reserve_ccy)
                d.risk_headroom_after_ccy = float(allocator_remaining)
                d.risk_metrics_snapshot["allocator_admitted"] = True
                METRIC_FTMO_ALLOCATOR_ADMITTED_TOTAL.labels(symbol=sym).inc()
            else:
                d.selected_exec = 0
                d.risk_blocked = True
                d.risk_block_reason = "FTMO_RESERVED_BUDGET_EXCEEDED"
                d.risk_metrics_snapshot["allocator_admitted"] = False
                d.risk_headroom_after_ccy = float(allocator_remaining)
                METRIC_RISK_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                METRIC_FTMO_ALLOCATOR_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()

        METRIC_FTMO_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(active_reserved_loss_ccy + newly_reserved_ccy))

    results: list[OcoPrediction] = []
    for d in decisions:
        if d.selected_exec == 1 and _state is not None:
            if allocator_enabled and d.risk_reserved and (d.risk_reserved_amount_ccy is not None):
                reservation_id = _state.create_ftmo_risk_reservation(
                    symbol=sym,
                    candidate_uid=d.candidate_uid,
                    reserved_loss_ccy=float(d.risk_reserved_amount_ccy),
                    barrier_pips=float(d.cand.barrier_pips),
                    cap_pips=float(_get_cap_pips(sym)),
                    cost_est_pips=float(d.features.cost_est_pips),
                    volume_units=float(requested_volume_units),
                    source="predict_allocator",
                    status="PENDING",
                )
                d.risk_reservation_id = reservation_id
                d.risk_metrics_snapshot["risk_reservation_id"] = reservation_id

            _state.log_audit_event(
                symbol=sym,
                candidate_uid=d.candidate_uid,
                pred_prob=d.pred_prob,
                threshold=d.curr_threshold,
                features=d.features,
                model_month=model_month,
            )

        results.append(
            OcoPrediction(
                symbol=sym,
                close_ts=close_ts,
                candidate_uid=d.candidate_uid,
                pred_prob=d.pred_prob,
                threshold_exec=d.curr_threshold,
                selected_exec=d.selected_exec,
                bar_ticks=int(d.cand.bar_ticks),
                horizon=int(d.cand.horizon),
                barrier_pips=float(d.cand.barrier_pips),
                cap_pips=_get_cap_pips(sym),
                threshold_source=d.curr_source,
                model_month=model_month,
                risk_blocked=d.risk_blocked,
                risk_block_reason=d.risk_block_reason,
                risk_metrics_snapshot=d.risk_metrics_snapshot,
                risk_reserved=d.risk_reserved,
                risk_reserved_amount_ccy=d.risk_reserved_amount_ccy,
                risk_headroom_after_ccy=d.risk_headroom_after_ccy,
                risk_rank_score=d.risk_rank_score,
                risk_reservation_id=d.risk_reservation_id,
            )
        )
    return results


@app.post("/trades/open")
async def open_trade(req: TradeOpenRequest):
    """Record an execution entry on the broker."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    internal_id = _state.open_trade(
        symbol=req.symbol,
        candidate_uid=req.candidate_uid,
        broker_pos_id=req.broker_pos_id,
        side=req.side,
        entry_price=req.entry_price,
        entry_ts=req.entry_ts,
        horizon=req.horizon,
    )
    if _config.ftmo_enabled and (_ftmo_profile is not None):
        _state.promote_ftmo_risk_reservation(
            broker_pos_id=req.broker_pos_id,
            reservation_id=req.reservation_id,
            candidate_uid=req.candidate_uid,
            symbol=req.symbol,
        )
    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, status="OPEN").inc()
    return {"status": "ok", "internal_trade_id": internal_id}


@app.get("/trades/active", response_model=list[ActiveTrade])
async def get_active_trades(symbol: str):
    """Fetch all OPEN trades for a symbol (used by cBot for recovery)."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    return _state.get_active_trades(symbol)


@app.post("/trades/touch")
async def touch_trade(req: TradeTouchRequest):
    """Record that a position's barrier was touched."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    sym = req.symbol.upper()
    res = _state._con.execute("SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [sym]).fetchone()
    touch_bar_id = res[0] if res and res[0] is not None else 0
    _state.touch_trade(req.broker_pos_id, touch_bar_id)
    return {"status": "ok"}


@app.post("/trades/update")
async def update_trade(req: TradeUpdateRequest):
    """Update a trade status (CLOSED/CANCELLED)."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    _state.update_trade(
        broker_pos_id=req.broker_pos_id,
        status=req.status.value,
        exit_price=req.exit_price,
        exit_ts=req.exit_ts,
        pnl_pips=req.pnl_pips,
    )
    if _config.ftmo_enabled and (_ftmo_profile is not None) and req.status.value in {"CLOSED", "CANCELLED"}:
        _state.release_ftmo_risk_reservation(
            broker_pos_id=req.broker_pos_id,
            reason=f"trade_{req.status.value.lower()}",
        )

    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, status=req.status.value).inc()
    if req.pnl_pips is not None:
        # Note: We need a way to look up the symbol from broker_pos_id if we want granular metrics here.
        # For now, we update a global or handle it in the background worker.
        pass

    return {"status": "ok"}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """System health: model validity, buffer depths."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    bar_counts: dict[str, int] = {}
    for sym in _config.symbols:
        bar_counts[sym] = _state.bar_count(sym, 100)

    return HealthResponse(
        status="ok" if _models else "no_models",
        utc_now=datetime.now(tz=timezone.utc),
        models_loaded=dict(_model_months),
        bar_counts=bar_counts,
    )


@app.get("/status")
async def status() -> list[StatusSymbol]:
    """Per-symbol detailed status."""
    out: list[StatusSymbol] = []
    for sym in _config.symbols:
        out.append(StatusSymbol(
            symbol=sym,
            bar_count=_state.bar_count(sym, 100) if _state else 0,
            model_loaded=sym in _models,
            model_month=_model_months.get(sym),
            has_threshold=bool(_thresholds.get(sym)),
        ))
    return out


@app.post("/reload")
async def reload_models() -> dict:
    """Hot-reload models from disk without restarting the server."""
    _load_models()
    return {"ok": True, "models_loaded": dict(_model_months)}


@app.post("/backfill", status_code=201)
async def backfill(req: BackfillRequest) -> dict:
    """Accept a batch of raw ticks, aggregate into bars, load into DuckDB.

    Called by the cBot on startup with ``MarketData.GetTicks()`` output.
    """
    if _state is None or not _aggregators:
        raise HTTPException(status_code=503, detail="Not initialized")

    bars = []
    for agg in _aggregators.values():
        bars.extend(agg.add_ticks(req.ticks))

    for bar in bars:
        _state.append_bar(bar)

    sym = req.symbol.upper()
    count = _state.bar_count(sym, req.bar_ticks)
    warmup_needed = max(_config.vol_window, _config.cost_window) + 1
    return {
        "ok": True,
        "symbol": sym,
        "ticks_received": len(req.ticks),
        "bars_created": len(bars),
        "bar_count": count,
        "warm": count >= warmup_needed,
    }


@app.post("/ticks", status_code=201)
async def ingest_tick(tick: IncomingTick) -> dict:
    """Accept a single live tick, buffer it, and auto-emit bars.

    Called by the cBot on each ``OnTick()`` event.
    """
    if _state is None or not _aggregators:
        raise HTTPException(status_code=503, detail="Not initialized")

    completed_bar_ticks = []
    bars = []
    for agg in _aggregators.values():
        bars.extend(agg.add_ticks([tick]))

    bar_completed = False
    for bar in bars:
        _state.append_bar(bar)
        completed_bar_ticks.append(bar.bar_ticks)
        bar_completed = True

    sym = tick.symbol.upper()
    return {
        "ok": True,
        "symbol": sym,
        "bar_completed": bar_completed,
        "completed_bar_ticks": completed_bar_ticks,
        "bar_count": _state.bar_count(sym, 100), # Return standard 100-tick count as baseline
    }
