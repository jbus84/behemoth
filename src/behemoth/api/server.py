"""FastAPI inference server for the OCO stop-limit strategy.

Endpoints:
    POST /bars         – Ingest a new tick bar from the active broker adapter
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
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field, model_validator

from src.behemoth.api.cache_manager import CacheManager
from src.behemoth.api.dashboard import router as dashboard_router
from src.behemoth.api.predict_orchestrator import PredictionOrchestrator
from src.behemoth.core.features import FeatureConfig
from src.behemoth.core.schemas import (
    AccountRiskSnapshotRequest,
    ActiveTrade,
    IncomingTick,
    IncomingTickBar,
    PredictResponse,
    TradeOpenRequest,
    TradeTouchRequest,
    TradeUpdateRequest,
)
from src.behemoth.risk.account import (
    AccountRiskDecision,
    AccountRiskProfile,
    evaluate_account_risk_decision,
    evaluate_account_risk_limits,
    evaluate_trade_risk_guard,
    load_account_risk_profile,
)
from src.behemoth.runtime.barrier_manager import BarrierManager
from src.behemoth.runtime.state import StateManager
from src.behemoth.runtime.tick_aggregator import TickAggregator

evaluate_account_limits = evaluate_account_risk_limits
evaluate_trade_guard = evaluate_trade_risk_guard

logger = logging.getLogger("behemoth.api")

# ── App ───────────────────────────────────────────────────────────────

# ── Global State ──────────────────────────────────────────────────────
#
# Historically these dependencies were spread across many module-level
# globals. ``_app_state`` (a typed RuntimeAppState) is the canonical home
# for them now; the individual globals below are kept as aliases for
# backward compat with the long tail of route handlers in this module
# that still read them directly. New code should prefer ``_app_state``.

from src.behemoth.api.runtime_app_state import RuntimeAppState

_app_state: RuntimeAppState = RuntimeAppState()


def _get_app_state() -> RuntimeAppState:
    """FastAPI dependency that returns the canonical runtime app state."""
    return _app_state


_state: StateManager | None = None
_barrier_manager: BarrierManager | None = None
_orchestrator: PredictionOrchestrator | None = None
_aggregators: dict[int, TickAggregator] = {}
_cache_manager: CacheManager = CacheManager([])
_models_dir: Path = Path("models/oco")
_account_risk_rules_path: Path = Path("configs/research/governance/account_risk/account_risk_rules.yaml")
_account_risk_profile: AccountRiskProfile | None = None
_historical_entries_loaded: int = 0
_historical_preflight_failed_checks: int = 0
_historical_preflight_summary: str = ""
_feed_state: dict[str, dict[str, Any]] = {}
_lifespan_ready: bool = False
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_HISTORICAL_PREDICTION_TOLERANCE_SEC = 30.0
_DEFAULT_FEATURE_CONFIG = FeatureConfig()


def _env_str(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return str(default)


def _env_bool(*keys: str, default: str = "false") -> bool:
    return _env_str(*keys, default=default).strip().lower() in {"1", "true", "yes", "y"}


def _env_int(*keys: str, default: str) -> int:
    return int(_env_str(*keys, default=default))


# ── Prometheus Metrics ────────────────────────────────────────────────
METRIC_INFERENCE_LATENCY = Histogram(
    "behemoth_inference_latency_seconds",
    "Time spent in CatBoost inference",
    ["symbol", "family"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

METRIC_TRADES_TOTAL = Counter(
    "behemoth_trades_total",
    "Total trade intents",
    ["symbol", "family", "status"]  # status: OPEN, FILLED, REJECTED, CLOSED, CANCELLED
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
    "Total account-risk blocked execution intents",
    ["symbol", "family", "reason"],
)

METRIC_ROLLING_THRESHOLD_DRIFT = Counter(
    "behemoth_rolling_threshold_drift_total",
    "Rolling threshold deviation vs static threshold_exec baseline",
    ["symbol", "candidate", "state"],
)

THRESHOLD_DRIFT_WARN_PP = 0.05


def _record_rolling_threshold_drift(
    *,
    symbol: str,
    candidate_uid: str,
    rolling: float,
    baseline: float,
) -> None:
    if baseline <= 0.0:
        return
    drift_pp = abs(float(rolling) - float(baseline))
    state = "drift" if drift_pp > THRESHOLD_DRIFT_WARN_PP else "ok"
    METRIC_ROLLING_THRESHOLD_DRIFT.labels(
        symbol=symbol.upper(), candidate=candidate_uid, state=state,
    ).inc()
    if state == "drift":
        logger.warning(
            "Rolling threshold drift for %s %s: rolling=%.4f baseline=%.4f drift=%.4f (band=%.2f)",
            symbol, candidate_uid, float(rolling), float(baseline), drift_pp, THRESHOLD_DRIFT_WARN_PP,
        )

METRIC_ACCOUNT_RISK_DAILY_HEADROOM = Gauge(
    "behemoth_account_risk_daily_loss_headroom",
    "Remaining buffered daily loss headroom in account currency units",
    ["symbol"],
)

METRIC_ACCOUNT_RISK_MAX_HEADROOM = Gauge(
    "behemoth_account_risk_max_loss_headroom",
    "Remaining buffered max loss headroom in account currency units",
    ["symbol"],
)

METRIC_ACCOUNT_RISK_RESERVED_LOSS_CCY = Gauge(
    "behemoth_account_risk_reserved_loss_ccy",
    "Active reserved account risk worst-case loss budget in account currency",
    ["symbol"],
)

METRIC_ACCOUNT_RISK_ALLOCATOR_BLOCKS_TOTAL = Counter(
    "behemoth_account_risk_allocator_blocks_total",
    "Total account risk allocator budget blocks",
    ["symbol", "family", "reason"],
)

METRIC_ACCOUNT_RISK_ALLOCATOR_ADMITTED_TOTAL = Counter(
    "behemoth_account_risk_allocator_admitted_total",
    "Total account risk allocator-admitted candidates",
    ["symbol", "family"],
)

METRIC_OPEN_POSITIONS_TOTAL = Gauge(
    "behemoth_open_positions_total",
    "Count of non-closed reservations (PENDING + OPEN)",
    ["symbol"],
)

METRIC_BROKER_OPEN_POSITIONS_TOTAL = Gauge(
    "behemoth_broker_open_positions_total",
    "Count of broker-confirmed open trades",
    ["symbol"],
)

METRIC_PENDING_BROKER_CONFIRM_POSITIONS_TOTAL = Gauge(
    "behemoth_pending_broker_confirm_positions_total",
    "Count of non-closed reservations still awaiting broker confirmation",
    ["symbol"],
)

METRIC_OPEN_POSITION_AGE_SECONDS = Gauge(
    "behemoth_open_position_age_seconds",
    "Wall-clock seconds since the oldest broker-confirmed open trade was created",
    ["symbol"],
)

METRIC_ESTIMATED_UNREALIZED_PIPS = Gauge(
    "behemoth_estimated_unrealized_pips",
    "Best-effort unrealized P&L in pips based on last known bar close price",
    ["symbol"],
)

METRIC_OPEN_POSITION_AGE_BARS = Gauge(
    "behemoth_open_position_age_bars",
    "Bars elapsed since the oldest broker-confirmed open trade entered",
    ["symbol"],
)

METRIC_OPEN_POSITION_BARS_REMAINING = Gauge(
    "behemoth_open_position_bars_remaining",
    "Bars remaining until the oldest broker-confirmed open trade reaches its horizon",
    ["symbol"],
)

METRIC_RESTART_VERDICT_ALLOWED = Gauge(
    "behemoth_restart_verdict_allowed",
    "1 if restart reconciliation verdict is ALLOW, 0 otherwise (UNKNOWN, RESTART_BLOCKED, etc)",
)


class AppConfig(BaseModel):
    """Runtime configuration for the inference server."""
    vol_window: int = _DEFAULT_FEATURE_CONFIG.vol_window
    cost_window: int = _DEFAULT_FEATURE_CONFIG.cost_window
    models_dir: str = Field(default_factory=lambda: os.getenv("BEHEMOTH_MODELS_DIR", "models/oco"))
    registry_path: str = Field(default_factory=lambda: os.getenv("BEHEMOTH_REGISTRY_PATH", "configs/research/governance/oco_rule_universe_registry.yaml"))
    symbols: list[str] = Field(
        default_factory=lambda: [
            str(sym).strip().upper()
            for sym in os.getenv(
                "BEHEMOTH_SYMBOLS",
                "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            ).split(",")
            if str(sym).strip()
        ]
    )
    persist_db_path: str | None = Field(
        default_factory=lambda: os.getenv("BEHEMOTH_STATE_DB", "data/db/behemoth_runtime.db")
    )
    account_risk_enabled: bool = Field(
        default_factory=lambda: _env_bool(
            "BEHEMOTH_ACCOUNT_RISK_ENABLED",
            default="true",
        )
    )
    account_risk_enforce_blocks: bool = Field(
        default_factory=lambda: _env_bool(
            "BEHEMOTH_ACCOUNT_RISK_ENFORCE_BLOCKS",
            default="true",
        )
    )
    account_risk_rules_path: str = Field(
        default_factory=lambda: _env_str(
            "BEHEMOTH_ACCOUNT_RISK_RULES_PATH",
            default="configs/research/governance/account_risk/account_risk_rules.yaml",
        )
    )
    account_risk_profile_id: str = Field(
        default_factory=lambda: _env_str(
            "BEHEMOTH_ACCOUNT_RISK_PROFILE_ID",
            default="ftmo_10k_challenge_2step",
        )
    )
    account_risk_trade_cost_gate_mode: str = Field(
        default_factory=lambda: _env_str(
            "BEHEMOTH_ACCOUNT_RISK_TRADE_COST_GATE_MODE",
            default="",
        )
        .strip()
        .lower()
    )
    account_risk_pending_reservation_ttl_sec: int = Field(
        default_factory=lambda: _env_int(
            "BEHEMOTH_ACCOUNT_RISK_PENDING_RESERVATION_TTL_SEC",
            default="1800",
        )
    )
    account_risk_fx_rate_max_age_sec: int = Field(
        default_factory=lambda: _env_int(
            "BEHEMOTH_ACCOUNT_RISK_FX_RATE_MAX_AGE_SEC",
            default="600",
        )
    )
    governance_mode: str = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_GOVERNANCE_MODE", "live")).strip().lower()
    )
    governance_history_dir: str = Field(
        default_factory=lambda: os.getenv(
            "BEHEMOTH_GOVERNANCE_HISTORY_DIR",
            "configs/research/governance/oco_history",
        )
    )
    governance_missing_month_policy: str = Field(
        default_factory=lambda: str(
            os.getenv("BEHEMOTH_GOVERNANCE_MISSING_MONTH_POLICY", "error")
        )
        .strip()
        .lower()
    )
    historical_preflight_mode: str = Field(
        default_factory=lambda: str(
            os.getenv("BEHEMOTH_HISTORICAL_PREFLIGHT_MODE", "error")
        )
        .strip()
        .lower()
    )
    historical_prediction_universe_mode: str = Field(
        default_factory=lambda: str(
            os.getenv(
                "BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE",
                "exact",
            )
        )
        .strip()
        .lower()
    )
    historical_prediction_payload_mode: str = Field(
        default_factory=lambda: str(
            os.getenv(
                "BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE",
                (
                    "locked"
                    if str(os.getenv("BEHEMOTH_GOVERNANCE_MODE", "live")).strip().lower()
                    in {"historical", "historical_auto"}
                    else "model"
                ),
            )
        )
        .strip()
        .lower()
    )
    historical_prediction_tolerance_sec: float = Field(
        default_factory=lambda: float(
            os.getenv(
                "BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC",
                (
                    "120.0"
                    if str(os.getenv("BEHEMOTH_GOVERNANCE_MODE", "live")).strip().lower()
                    in {"historical", "historical_auto"}
                    else "30.0"
                ),
            )
        )
    )
    historical_prediction_ordinal_tolerance: int = Field(
        default_factory=lambda: int(
            os.getenv("BEHEMOTH_HISTORICAL_PREDICTION_ORDINAL_TOLERANCE", "0")
        )
    )
    force_model_month: str = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_FORCE_MODEL_MONTH", "")).strip()
    )
    record_raw_ticks: bool = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_RECORD_RAW_TICKS", "true")).strip().lower()
        in {"1", "true", "yes", "y"}
    )
    debug_run_id: str = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_DEBUG_RUN_ID", "")).strip()
    )
    debug_http_trace: bool = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_DEBUG_HTTP_TRACE", "false")).strip().lower()
        in {"1", "true", "yes", "y"}
    )
    debug_http_trace_path: str = Field(
        default_factory=lambda: str(os.getenv("BEHEMOTH_DEBUG_HTTP_TRACE_PATH", "")).strip()
    )
    dukascopy_ticks_dir: str = Field(
        default_factory=lambda: os.getenv(
            "BEHEMOTH_DUKASCOPY_TICKS_DIR",
            "/Users/danielfisher/Desktop/dukascopy_ticks",
        )
    )


_config = AppConfig()


def _runtime_state_db_path() -> Path:
    if _state is not None:
        stub_path = getattr(_state, "db_path", None)
        if stub_path:
            return Path(str(stub_path))
    return Path(_env_str("BEHEMOTH_STATE_DB", default="data/db/behemoth_runtime.db"))


def _restart_reconciliation_report_path() -> Path:
    return _runtime_state_db_path().parent / "live_restart_reconciliation.json"


def _load_restart_reconciliation_report() -> dict[str, Any] | None:
    path = _restart_reconciliation_report_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("Failed to parse restart reconciliation report: %s", path, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


def _build_open_positions_summary(
    state: StateManager,
    now: datetime,
    aggregators: dict[int, TickAggregator] | None = None,
) -> dict:
    """Compute cross-symbol open position summary from DB state.

    Side-effect: updates METRIC_OPEN_POSITIONS_TOTAL, METRIC_OPEN_POSITION_AGE_SECONDS,
    METRIC_BROKER_OPEN_POSITIONS_TOTAL, METRIC_OPEN_POSITION_AGE_BARS, and
    METRIC_ESTIMATED_UNREALIZED_PIPS for every known symbol.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    reservations = state.list_active_account_risk_reservations()

    # Group by symbol for gauge updates
    by_symbol: dict[str, list[dict]] = {}
    for r in reservations:
        by_symbol.setdefault(r["symbol"], []).append(r)

    positions: list[dict] = []
    broker_open_count_by_symbol: dict[str, int] = {}
    for sym, sym_reservations in by_symbol.items():
        price_data = state.get_last_bar_close_price(sym)
        last_tick_ts: datetime | None = price_data[1] if price_data else None
        last_tick_age_seconds: float | None = (
            round((now - last_tick_ts).total_seconds(), 1) if last_tick_ts else None
        )
        # Prefer the latest buffered tick bid (most recent received tick) over the
        # last completed bar close — bars can be several minutes old during quiet
        # periods and will invert the sign of unrealized pips when price crosses entry.
        last_tick_price: float | None = None
        if aggregators:
            for agg in aggregators.values():
                bid = agg.latest_bid(sym)
                if bid is not None:
                    last_tick_price = bid
                    break
        if last_tick_price is None:
            last_tick_price = price_data[0] if price_data else None

        sym_unrealized_total = 0.0
        for r in sym_reservations:
            entry_price: float | None = None
            if r["broker_pos_id"]:
                entry_price = state.get_open_trade_entry_price(r["reservation_id"])

            estimated_unrealized_pips: float | None = None
            if entry_price is not None and last_tick_price is not None:
                pip_size = _pip_size_for_symbol(sym)
                if r["side"] == "BUY":
                    estimated_unrealized_pips = round(
                        (last_tick_price - entry_price) / pip_size, 1
                    )
                else:
                    estimated_unrealized_pips = round(
                        (entry_price - last_tick_price) / pip_size, 1
                    )
                sym_unrealized_total += estimated_unrealized_pips

            created_ts: datetime | None = r["created_ts"]
            open_minutes: float | None = (
                round((now - created_ts).total_seconds() / 60.0, 1)
                if created_ts
                else None
            )
            positions.append(
                {
                    "symbol": sym,
                    "direction": r["side"],
                    "status": r["status"],
                    "broker_confirmed": r["broker_pos_id"] is not None,
                    "broker_pos_id": r["broker_pos_id"],
                    "open_since_utc": created_ts.isoformat() if created_ts else None,
                    "open_minutes": open_minutes,
                    "entry_price": entry_price,
                    "last_tick_price": last_tick_price,
                    "last_tick_age_seconds": last_tick_age_seconds,
                    "estimated_unrealized_pips": estimated_unrealized_pips,
                }
            )

        METRIC_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(len(sym_reservations))
        # Oldest broker-confirmed trade metrics are keyed off the same confirmed-trade set.
        confirmed_reservations = {
            str(r["broker_pos_id"]): r
            for r in sym_reservations
            if r.get("broker_pos_id") is not None and r.get("created_ts") is not None
        }
        active_trades = state.get_active_trades(sym)
        broker_open_count_by_symbol[sym] = len(active_trades)
        METRIC_BROKER_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(len(active_trades))
        METRIC_PENDING_BROKER_CONFIRM_POSITIONS_TOTAL.labels(symbol=sym).set(
            max(0, len(sym_reservations) - len(active_trades))
        )
        oldest_confirmed_created_ts = min(
            (
                confirmed_reservations[str(trade["broker_pos_id"])]["created_ts"]
                for trade in active_trades
                if str(trade["broker_pos_id"]) in confirmed_reservations
            ),
            default=None,
        )
        METRIC_OPEN_POSITION_AGE_SECONDS.labels(symbol=sym).set(
            (now - oldest_confirmed_created_ts).total_seconds()
            if oldest_confirmed_created_ts
            else 0.0
        )
        METRIC_ESTIMATED_UNREALIZED_PIPS.labels(symbol=sym).set(sym_unrealized_total)

        # Bars elapsed / remaining for the oldest broker-confirmed (OPEN) trade on this symbol
        if active_trades:
            oldest_trade = min(active_trades, key=lambda t: t["entry_bar_id"])
            current_bar = state.get_latest_bar_id(sym)
            bars_elapsed = max(0, current_bar - oldest_trade["entry_bar_id"])
            bars_remaining = max(0, oldest_trade["horizon"] - bars_elapsed)
            METRIC_OPEN_POSITION_AGE_BARS.labels(symbol=sym).set(bars_elapsed)
            METRIC_OPEN_POSITION_BARS_REMAINING.labels(symbol=sym).set(bars_remaining)
        else:
            METRIC_OPEN_POSITION_AGE_BARS.labels(symbol=sym).set(0)
            METRIC_OPEN_POSITION_BARS_REMAINING.labels(symbol=sym).set(0)

    # Zero out gauges for symbols with no open positions
    for sym in state.get_all_symbols():
        if sym not in by_symbol:
            METRIC_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(0)
            METRIC_BROKER_OPEN_POSITIONS_TOTAL.labels(symbol=sym).set(0)
            METRIC_PENDING_BROKER_CONFIRM_POSITIONS_TOTAL.labels(symbol=sym).set(0)
            METRIC_OPEN_POSITION_AGE_SECONDS.labels(symbol=sym).set(0)
            METRIC_OPEN_POSITION_AGE_BARS.labels(symbol=sym).set(0)
            METRIC_OPEN_POSITION_BARS_REMAINING.labels(symbol=sym).set(0)
            METRIC_ESTIMATED_UNREALIZED_PIPS.labels(symbol=sym).set(0)

    broker_confirmed = sum(broker_open_count_by_symbol.values())
    return {
        "as_of_utc": now.isoformat(),
        "total_open": len(positions),
        "broker_confirmed": broker_confirmed,
        "pending_broker_confirm": len(positions) - broker_confirmed,
        "positions": positions,
    }


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event."""
    global _state, _barrier_manager, _orchestrator, _aggregators, _feed_state, _lifespan_ready
    global _models_dir, _account_risk_rules_path, _account_risk_profile
    global _historical_entries_loaded, _historical_preflight_failed_checks, _historical_preflight_summary

    # Start background monitor
    monitor_task = asyncio.create_task(_monitor_ledger())
    position_summary_task = asyncio.create_task(_write_position_summary_loop())
    orphan_cleanup_task = asyncio.create_task(_orphan_reservation_cleanup_loop())

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
    _barrier_manager = BarrierManager()
    legacy_rejected_scans = _barrier_manager.reject_legacy_active_scans()
    if legacy_rejected_scans:
        logger.warning(
            "Rejected %d legacy active barrier scans missing side-aware signal closes",
            len(legacy_rejected_scans),
        )
        if _config.account_risk_enabled:
            for scan in legacy_rejected_scans:
                reservation_id = scan.get("reservation_id")
                if reservation_id:
                    _state.release_account_risk_reservation(
                        reservation_id=str(reservation_id),
                        reason="legacy_barrier_scan_migration",
                    )
    _feed_state = {}
    try:
        _aggregators = {}
        _cache_manager.reset_all()
        # Model-serving is a placeholder pending boostlss_xs wiring (see
        # docs/superpowers/plans/2026-07-02-repo-cleanup.md). No model is loaded;
        # /predict returns an empty prediction list until a model is wired in.
        _historical_entries_loaded = 0
        _historical_preflight_failed_checks = 0
        _historical_preflight_summary = ""
        unique_bar_ticks = {100}
        for bt in unique_bar_ticks:
            _aggregators[bt] = TickAggregator(bar_ticks=bt)
            logger.info("Initialized TickAggregator for %d ticks", bt)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Runtime scaffold startup failed: %s", exc)
        raise
    _models_dir = Path(_config.models_dir)
    _load_models()
    _load_seed_files()
    _account_risk_rules_path = Path(_config.account_risk_rules_path)
    _account_risk_profile = None
    try:
        _account_risk_profile = load_account_risk_profile(
            _account_risk_rules_path,
            _config.account_risk_profile_id,
        )
        if str(_config.account_risk_trade_cost_gate_mode).strip():
            _account_risk_profile = replace(
                _account_risk_profile,
                cost_gate=replace(
                    _account_risk_profile.cost_gate,
                    trade_cost_gate_mode=str(_config.account_risk_trade_cost_gate_mode).strip().lower(),
                ),
            )
        logger.info(
            "Loaded account risk profile %s from %s",
            _account_risk_profile.profile_id,
            _account_risk_rules_path,
        )
    except Exception as exc:
        logger.error("Failed to load account risk rules: %s", exc)

    # PredictionOrchestrator is not constructed in placeholder mode: no
    # registry is loaded, so /predict short-circuits to an empty response
    # (handler-level guard) rather than entering the 7-step pipeline. The
    # orchestrator symbol is retained for the Task 2.3 handler rewrite.
    _orchestrator = None
    logger.info("PredictionOrchestrator not initialized (placeholder mode, no registry)")

    # Sync the typed RuntimeAppState container with the freshly-built globals.
    # New code should prefer ``_app_state``; existing routes still use the
    # individual globals above. Both views point at the same instances.
    _app_state.state = _state
    _app_state.barrier_manager = _barrier_manager
    _app_state.orchestrator = _orchestrator
    _app_state.account_risk_profile = _account_risk_profile
    _app_state.aggregators = _aggregators
    _app_state.feed_state = _feed_state
    _app_state.models_dir = _models_dir
    _app_state.account_risk_rules_path = _account_risk_rules_path
    _app_state.historical_entries_loaded = _historical_entries_loaded

    logger.info("Behemoth API started. Models dir: %s", _models_dir)
    _lifespan_ready = True
    _app_state.lifespan_ready = True
    yield
    _lifespan_ready = False
    _app_state.lifespan_ready = False
    monitor_task.cancel()
    position_summary_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task
    with suppress(asyncio.CancelledError):
        await position_summary_task

    _barrier_manager = None
    if _state and hasattr(_state, "close"):
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
                _sync_equity_pips_metrics(_state.get_ledger_stats())
                if _config.account_risk_enabled and (_account_risk_profile is not None):
                    include_pending = bool(_account_risk_profile.allocator.allocator_reserve_pending)
                    include_open = bool(_account_risk_profile.allocator.allocator_reserve_open)
                    for sym in _config.symbols:
                        reserved = _state.sum_active_account_risk_reserved_loss_ccy(
                            symbol=sym,
                            include_pending=include_pending,
                            include_open=include_open,
                        )
                        METRIC_ACCOUNT_RISK_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(reserved))
        except Exception as e:
            logger.error("Ledger monitor error: %s", e)
        await asyncio.sleep(60)


def _sync_equity_pips_metrics(stats: list[dict[str, Any]]) -> None:
    """Rebuild realized-PnL gauges from the current ledger snapshot only."""
    METRIC_EQUITY_PIPS.clear()
    for stat in stats:
        METRIC_EQUITY_PIPS.labels(symbol=stat["symbol"]).set(stat["total_pnl"])


async def _write_position_summary_loop() -> None:
    """Background task: write live_position_summary.json every 5 seconds."""
    while True:
        try:
            if _state and _config.persist_db_path:
                now = datetime.now(tz=timezone.utc)
                summary = _build_open_positions_summary(_state, now, _aggregators)
                summary_path = (
                    Path(_config.persist_db_path).parent / "live_position_summary.json"
                )
                summary_path.write_text(
                    json.dumps(summary, indent=2, default=str), encoding="utf-8"
                )
        except Exception as e:
            logger.error("Position summary writer error: %s", e)
        await asyncio.sleep(5)


async def _orphan_reservation_cleanup_loop() -> None:
    """Background task: release PENDING reservations that have no active barrier scan.

    A reservation is considered orphaned if it has been PENDING for longer than
    order_ttl_seconds and no HOLDING/SCANNING barrier scan references its reservation_id.
    This covers the race where predict_allocator creates a reservation but the Java side
    never starts a scan (or the scan expired without linking back to the reservation).
    """
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        try:
            if _state is None or _barrier_manager is None:
                continue
            now = datetime.now(tz=timezone.utc)
            ttl_seconds = _config.account_risk_pending_reservation_ttl_sec
            reservations = _state.list_active_account_risk_reservations()
            for r in reservations:
                if r["status"] != "PENDING":
                    continue
                created_ts: datetime | None = r["created_ts"]
                if created_ts is None:
                    continue
                age_seconds = (now - created_ts).total_seconds()
                if age_seconds < ttl_seconds:
                    continue
                # Check if any active (SCANNING/HOLDING) scan references this reservation
                scan = _barrier_manager.get_scan_by_reservation_id(r["reservation_id"])
                if scan is not None:
                    continue
                # Orphaned — release it
                released = _state.release_risk_reservation(
                    reservation_id=r["reservation_id"],
                    reason="orphaned_no_scan_ttl_expired",
                )
                if released:
                    logger.warning(
                        "Released orphaned PENDING reservation %s for %s (age=%.0fs, ttl=%ss)",
                        r["reservation_id"],
                        r["symbol"],
                        age_seconds,
                        ttl_seconds,
                    )
        except Exception as e:
            logger.error("Orphan reservation cleanup error: %s", e)


app = FastAPI(
    title="Behemoth OCO Inference API",
    version="0.1.0",
    description="Production inference server for the tick-based OCO stop-limit strategy.",
    lifespan=lifespan,
)

app.include_router(dashboard_router)


def _load_models() -> None:
    """No-op placeholder. Model-serving was removed with the tick-opportunity-mining
    pipeline; /predict returns empty predictions until boostlss_xs is wired in."""
    _cache_manager.reset_all()
    logger.info("Model loading skipped — placeholder predict path active (no model wired).")

def _load_seed_files(seed_dir: Path | None = None) -> None:
    """Load pre-computed threshold seed parquets into audit_logs."""
    import pandas as pd

    if _state is None:
        logger.warning("State manager not initialized — skipping seed load")
        return
    if seed_dir is None:
        seed_dir = Path(os.getenv("BEHEMOTH_SEED_DIR", "data/runtime/seed"))
    if not seed_dir.exists():
        logger.info("No seed directory at %s — skipping seed load", seed_dir)
        return
    parquets = sorted(seed_dir.glob("*_threshold_seed.parquet"))
    if not parquets:
        logger.info("No seed parquets found in %s", seed_dir)
        return
    # Clear any previously loaded seed rows to ensure idempotent restarts
    _state.clear_audit_logs_by_run_id("threshold_seed")
    total = 0
    for pq_path in parquets:
        try:
            df = pd.read_parquet(pq_path)
            if df.empty:
                continue
            events = []
            for row in df.itertuples(index=False):
                close_ts = row.close_ts
                if hasattr(close_ts, "to_pydatetime"):
                    close_ts = close_ts.to_pydatetime()
                events.append((
                    close_ts,
                    str(row.symbol),
                    str(row.candidate_uid),
                    float(row.pred_prob),
                    float(row.threshold),
                    str(row.features_json),
                    str(row.model_month),
                    str(row.run_id),
                ))
            _state.log_audit_event_batch(events)
            total += len(events)
            logger.info("Loaded %d seed events from %s", len(events), pq_path.name)
        except Exception as exc:
            logger.error("Failed to load seed file %s: %s", pq_path.name, exc)
    logger.info("Seed loading complete: %d total events", total)


def _pip_size_for_symbol(sym: str) -> float:
    return 0.01 if sym.upper().endswith("JPY") else 0.0001


def _parse_fx_ccy(sym: str) -> tuple[str, str] | None:
    s = str(sym).upper().strip()
    if len(s) < 6:
        return None
    base = s[:3]
    quote = s[3:6]
    if not (base.isalpha() and quote.isalpha()):
        return None
    return base, quote


def _latest_tick_price_snapshot(sym: str) -> dict[str, Any] | None:
    if _state is None:
        return None
    result = _state.get_latest_tick_snapshot(sym)
    if result is None:
        return None
    price, close_ts = result
    return {"symbol": sym.upper(), "price": price, "close_ts": close_ts}


def _snapshot_age_sec(snapshot: dict[str, Any], *, now_utc: datetime) -> float | None:
    ts = snapshot.get("close_ts")
    if not isinstance(ts, datetime):
        return None
    now = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
    delta = (now - ts).total_seconds()
    return max(0.0, float(delta))


def _quote_to_usd_rate(
    quote_ccy: str,
    *,
    now_utc: datetime,
    max_age_sec: int,
) -> dict[str, Any] | None:
    q = str(quote_ccy).upper().strip()
    if q == "USD":
        return {
            "conversion_pair": "USDUSD",
            "conversion_rate": 1.0,
            "conversion_age_sec": 0.0,
        }

    direct_sym = f"{q}USD"
    direct = _latest_tick_price_snapshot(direct_sym)
    if direct is not None:
        age = _snapshot_age_sec(direct, now_utc=now_utc)
        if (age is None) or (age <= float(max_age_sec)):
            return {
                "conversion_pair": direct_sym,
                "conversion_rate": float(direct["price"]),
                "conversion_age_sec": age if age is not None else 0.0,
            }

    inverse_sym = f"USD{q}"
    inverse = _latest_tick_price_snapshot(inverse_sym)
    if inverse is not None:
        px = max(float(inverse["price"]), 1e-12)
        age = _snapshot_age_sec(inverse, now_utc=now_utc)
        if (age is None) or (age <= float(max_age_sec)):
            return {
                "conversion_pair": inverse_sym,
                "conversion_rate": 1.0 / px,
                "conversion_age_sec": age if age is not None else 0.0,
            }
    return None


def _pip_value_per_unit_usd(
    sym: str,
    *,
    now_utc: datetime,
    max_age_sec: int,
) -> dict[str, Any]:
    pair = _parse_fx_ccy(sym)
    if pair is None:
        return {
            "pip_value_per_unit_usd": None,
            "conversion_status": "invalid_symbol",
            "conversion_pair": None,
            "conversion_rate": None,
            "conversion_age_sec": None,
        }

    base, quote = pair
    pip = _pip_size_for_symbol(sym)

    if quote == "USD":
        return {
            "pip_value_per_unit_usd": float(pip),
            "conversion_status": "direct_quote_usd",
            "conversion_pair": "USDUSD",
            "conversion_rate": 1.0,
            "conversion_age_sec": 0.0,
        }

    if base == "USD":
        snap = _latest_tick_price_snapshot(sym)
        if snap is None:
            return {
                "pip_value_per_unit_usd": None,
                "conversion_status": "missing_usd_base_spot",
                "conversion_pair": sym.upper(),
                "conversion_rate": None,
                "conversion_age_sec": None,
            }
        age = _snapshot_age_sec(snap, now_utc=now_utc)
        if (age is not None) and (age > float(max_age_sec)):
            return {
                "pip_value_per_unit_usd": None,
                "conversion_status": "stale_usd_base_spot",
                "conversion_pair": sym.upper(),
                "conversion_rate": float(snap["price"]),
                "conversion_age_sec": float(age),
            }
        px = max(float(snap["price"]), 1e-12)
        return {
            "pip_value_per_unit_usd": float(pip) / px,
            "conversion_status": "direct_base_usd",
            "conversion_pair": sym.upper(),
            "conversion_rate": float(snap["price"]),
            "conversion_age_sec": age if age is not None else 0.0,
        }

    rate = _quote_to_usd_rate(
        quote,
        now_utc=now_utc,
        max_age_sec=max_age_sec,
    )
    if rate is None:
        return {
            "pip_value_per_unit_usd": None,
            "conversion_status": "missing_or_stale_cross_rate",
            "conversion_pair": None,
            "conversion_rate": None,
            "conversion_age_sec": None,
        }
    return {
        "pip_value_per_unit_usd": float(pip) * float(rate["conversion_rate"]),
        "conversion_status": "cross_quote_to_usd",
        "conversion_pair": str(rate["conversion_pair"]),
        "conversion_rate": float(rate["conversion_rate"]),
        "conversion_age_sec": float(rate["conversion_age_sec"]),
    }


def _as_utc_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _effective_run_id(*values: Any) -> str | None:
    for raw in values:
        txt = str(raw or "").strip()
        if txt:
            return txt
    txt = str(_config.debug_run_id or "").strip()
    return txt or None


def _json_ready(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return _as_utc_ts(value).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _append_http_trace(
    *,
    endpoint: str,
    phase: str,
    run_id: str | None = None,
    symbol: str | None = None,
    request_payload: Any = None,
    response_payload: Any = None,
    status_code: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if (not _config.debug_http_trace) or (not str(_config.debug_http_trace_path).strip()):
        return
    path = Path(str(_config.debug_http_trace_path))
    record = {
        "ts_utc": datetime.now(tz=timezone.utc).isoformat(),
        "endpoint": str(endpoint),
        "phase": str(phase),
        "run_id": _effective_run_id(run_id),
        "symbol": str(symbol).upper().strip() if str(symbol or "").strip() else None,
        "status_code": int(status_code) if status_code is not None else None,
        "request": _json_ready(request_payload),
        "response": _json_ready(response_payload),
        "extra": _json_ready(extra or {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        logger.debug("Failed to append debug HTTP trace: path=%s", path, exc_info=True)


def _new_feed_tracker() -> dict[str, Any]:
    return {
        "total_received": 0,
        "total_accepted": 0,
        "total_dropped": 0,
        "total_batches": 0,
        "duplicate_timestamps": 0,
        "monotonic_violations": 0,
        "duplicate_client_tick_seq": 0,
        "client_seq_violations": 0,
        "symbol_tick_seq": 0,
        "last_client_tick_seq": None,
        "last_tick_ts_utc": None,
        "last_ingest_utc": None,
        "last_drop_reason": None,
    }


def _get_feed_tracker(symbol: str) -> dict[str, Any]:
    sym = str(symbol).upper().strip()
    row = _feed_state.get(sym)
    if row is None:
        row = _new_feed_tracker()
        _feed_state[sym] = row
    return row


def _resolve_account_risk_eval(
    sym: str,
    now_utc: datetime,
    *,
    account_risk_enabled_effective: bool,
) -> AccountRiskDecision:
    eval_out = evaluate_account_risk_decision(
        profile=_account_risk_profile,
        state_reader=_state,
        symbol=sym,
        now_utc=now_utc,
        enabled=account_risk_enabled_effective,
    )

    if eval_out.daily_loss_headroom is not None:
        METRIC_ACCOUNT_RISK_DAILY_HEADROOM.labels(symbol=sym).set(float(eval_out.daily_loss_headroom))
    if eval_out.max_loss_headroom is not None:
        METRIC_ACCOUNT_RISK_MAX_HEADROOM.labels(symbol=sym).set(float(eval_out.max_loss_headroom))
    return eval_out


def _account_risk_limits_payload() -> AccountRiskLimitsResponse:
    if (not _config.account_risk_enabled) or (_account_risk_profile is None):
        return AccountRiskLimitsResponse(enabled=False)
    prof = _account_risk_profile
    return AccountRiskLimitsResponse(
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
            "trade_cost_gate_mode": prof.cost_gate.trade_cost_gate_mode,
            "commission_round_turn_pips": prof.cost_gate.commission_round_turn_pips,
            "slippage_floor_pips": prof.cost_gate.slippage_floor_pips,
            "min_edge_buffer_pips": prof.cost_gate.min_edge_buffer_pips,
            "max_cost_to_barrier_ratio": prof.cost_gate.max_cost_to_barrier_ratio,
            "require_account_snapshot": prof.cost_gate.require_account_snapshot,
            "replay_round_trip_cost_pips": prof.cost_gate.replay_round_trip_cost_pips,
            "replay_slippage_floor_pips": prof.cost_gate.replay_slippage_floor_pips,
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
    """Prediction request with explicit intended size for account-risk allocation."""
    model_config = {"populate_by_name": True}

    symbol: str
    account_risk_enabled_override: bool | None = Field(
        default=None,
        alias="accountRiskEnabledOverride",
        description="Request-scoped account-risk guard toggle.",
    )
    risk_enabled_override: bool | None = Field(
        default=None,
        alias="riskEnabledOverride",
        description="Broker-neutral request-scoped account-risk guard toggle.",
    )
    requested_volume_units: float | None = Field(
        default=None,
        alias="requestedVolumeUnits",
        gt=0.0,
        description="Intended execution size in broker volume units.",
    )
    requested_lot_size: float | None = Field(
        default=None,
        alias="requestedLotSize",
        gt=0.0,
        description="Optional intended lot size (converted to units using 100k FX lot).",
    )
    completed_bar_ticks: list[int] = Field(
        default_factory=list,
        alias="completedBarTicks",
        description=(
            "Bar-tick granularities that just completed on the caller side "
            "(e.g. [100], [100,1000]). When provided, prediction is scoped to "
            "matching candidate bar_ticks only."
        ),
    )
    bar_ordinals: dict[str, int] | None = Field(
        default=None,
        alias="barOrdinals",
        description=(
            "Map from bar_ticks (string key) to the 0-indexed count of bars of "
            "that granularity closed since session start. Used by ordinal universe "
            "gate mode to match candidates by position rather than timestamp."
        ),
    )
    run_id: str | None = Field(default=None, alias="runId")

    @model_validator(mode="after")
    def _validate_risk_override(self) -> PredictRequest:
        if self.risk_enabled_override is None and self.account_risk_enabled_override is None:
            raise ValueError("One of risk_enabled_override or account_risk_enabled_override is required")
        return self

    def effective_risk_enabled_override(self) -> bool:
        if self.risk_enabled_override is not None:
            return bool(self.risk_enabled_override)
        if self.account_risk_enabled_override is not None:
            return bool(self.account_risk_enabled_override)
        raise ValueError("One of risk_enabled_override or account_risk_enabled_override is required")


class WarmupRequest(BaseModel):
    symbol: str
    run_id: str = "warmup"


class SeedAuditHistoryRequest(BaseModel):
    symbols: list[str] | None = None
    days_back: int = 20
    run_id: str = "audit_seed"
    train_predictions_dir: str | None = None
    test_month_start: str | None = None


class HealthResponse(BaseModel):
    status: str
    utc_now: datetime
    models_loaded: dict[str, str]
    bar_ticks: dict[str, list[int]]
    bar_counts: dict[str, int]
    governance_dir: str
    model_cache_entries: int = 0
    governance_mode: str | None = None
    governance_missing_month_policy: str | None = None
    historical_locks_loaded: int | None = None
    historical_preflight_failed_checks: int | None = None
    historical_preflight_summary: str | None = None


class StatusSymbolFamily(BaseModel):
    family: str
    model_loaded: bool
    model_month: str | None = None


class StatusSymbol(BaseModel):
    symbol: str
    bar_ticks: list[int]
    bar_count: int
    governance_dir: str
    model_loaded: bool
    model_month: str | None = None
    has_threshold: bool
    deployment_state: str
    restart_verdict: str | None = None
    restart_reasons: list[str] = Field(default_factory=list)
    families: list[StatusSymbolFamily] = Field(default_factory=list)


class FeedStatusSymbol(BaseModel):
    symbol: str
    total_received: int = 0
    total_accepted: int = 0
    total_dropped: int = 0
    total_batches: int = 0
    duplicate_timestamps: int = 0
    monotonic_violations: int = 0
    duplicate_client_tick_seq: int = 0
    client_seq_violations: int = 0
    symbol_tick_seq: int = 0
    last_client_tick_seq: int | None = None
    last_tick_ts_utc: datetime | None = None
    last_ingest_utc: datetime | None = None
    last_drop_reason: str | None = None


class FeedStatusResponse(BaseModel):
    as_of_utc: datetime
    governance_mode: str
    record_raw_ticks: bool
    symbols: list[FeedStatusSymbol]


class BackfillRequest(BaseModel):
    """Batch of raw ticks for instant warmup."""
    symbol: str
    bar_ticks: int = 100
    ticks: list[IncomingTick]
    run_id: str | None = None


class TickBatchRequest(BaseModel):
    """Batch of live ticks with optional symbol-level assertion."""
    symbol: str | None = None
    ticks: list[IncomingTick]
    run_id: str | None = None


class AccountRiskLimitsResponse(BaseModel):
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


class AccountRiskStatusResponse(BaseModel):
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


class AccountRiskReservationReleaseRequest(BaseModel):
    symbol: str | None = None
    candidate_uid: str | None = None
    broker_pos_id: str | None = None
    reservation_id: str | None = None
    reason: str | None = None
    family: str | None = None


class AccountRiskReservationsStatusResponse(BaseModel):
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


@app.post("/risk/account_risk/snapshot", status_code=201)
async def ingest_account_risk_snapshot(req: AccountRiskSnapshotRequest) -> dict[str, Any]:
    """Ingest account balance/equity snapshots emitted by cBot."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    run_id = _effective_run_id(req.run_id)
    _append_http_trace(
        endpoint="/risk/account_risk/snapshot",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
    )
    ts = req.snapshot_ts or datetime.now(tz=timezone.utc)
    _state.record_account_risk_snapshot(
        symbol=req.symbol,
        balance=float(req.balance),
        equity=float(req.equity),
        snapshot_ts=ts,
    )
    out = {
        "ok": True,
        "symbol": req.symbol.upper(),
        "snapshot_ts": ts,
    }
    _append_http_trace(
        endpoint="/risk/account_risk/snapshot",
        phase="response",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        response_payload=out,
        status_code=201,
    )
    return out


@app.post("/risk/account/snapshot", status_code=201)
async def ingest_account_snapshot(req: AccountRiskSnapshotRequest) -> dict[str, Any]:
    """Ingest broker-neutral account balance/equity snapshots emitted by an adapter."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    run_id = _effective_run_id(req.run_id)
    _append_http_trace(
        endpoint="/risk/account/snapshot",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
    )
    ts = req.snapshot_ts or datetime.now(tz=timezone.utc)
    _state.record_account_snapshot(
        symbol=req.symbol,
        balance=float(req.balance),
        equity=float(req.equity),
        snapshot_ts=ts,
    )
    out = {
        "ok": True,
        "symbol": req.symbol.upper(),
        "snapshot_ts": ts,
    }
    _append_http_trace(
        endpoint="/risk/account/snapshot",
        phase="response",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        response_payload=out,
        status_code=201,
    )
    return out


@app.get("/risk/account_risk/limits", response_model=AccountRiskLimitsResponse)
async def get_account_risk_limits() -> AccountRiskLimitsResponse:
    """Return active account-risk profile limits and internal buffered thresholds."""
    return _account_risk_limits_payload()


@app.get("/risk/account/limits", response_model=AccountRiskLimitsResponse)
async def get_account_limits() -> AccountRiskLimitsResponse:
    """Return active broker-neutral account-risk limits and internal thresholds."""
    return _account_risk_limits_payload()


@app.get("/risk/account_risk/status", response_model=AccountRiskStatusResponse)
async def get_account_risk_status(symbol: str | None = None) -> AccountRiskStatusResponse:
    """Return current account-risk guardrail status and account headroom."""
    sym = str(symbol or "").strip().upper() or None
    now_utc = datetime.now(tz=timezone.utc)
    eval_out = _resolve_account_risk_eval(
        sym or "ALL",
        now_utc,
        account_risk_enabled_effective=bool(_config.account_risk_enabled),
    )
    return AccountRiskStatusResponse(
        enabled=bool(eval_out.enabled),
        symbol=sym,
        profile_id=eval_out.profile_id,
        as_of_utc=now_utc,
        trading_day_id=eval_out.trading_day_id,
        allow_trading=bool(eval_out.allow_trading),
        block_reason=eval_out.block_reason,
        snapshot_available=bool(eval_out.snapshot_available),
        balance=eval_out.balance,
        equity=eval_out.equity,
        day_start_balance=eval_out.day_start_balance,
        daily_loss_used=eval_out.daily_loss_used,
        max_loss_used=eval_out.max_loss_used,
        daily_loss_headroom=eval_out.daily_loss_headroom,
        max_loss_headroom=eval_out.max_loss_headroom,
    )


@app.get("/risk/account/status", response_model=AccountRiskStatusResponse)
async def get_account_status(symbol: str | None = None) -> AccountRiskStatusResponse:
    """Return current broker-neutral account-risk status and account headroom."""
    return await get_account_risk_status(symbol)


@app.get("/risk/account_risk/reservations/status", response_model=AccountRiskReservationsStatusResponse)
async def get_account_risk_reservations_status(
    symbol: str | None = None,
    family: str | None = None,
) -> AccountRiskReservationsStatusResponse:
    """Return active account-risk reservation totals and rows."""
    sym = str(symbol or "").strip().upper() or None
    fam = str(family or "").strip() or None
    if (not _config.account_risk_enabled) or (_account_risk_profile is None) or (_state is None):
        return AccountRiskReservationsStatusResponse(enabled=False, symbol=sym)
    include_pending = bool(_account_risk_profile.allocator.allocator_reserve_pending)
    include_open = bool(_account_risk_profile.allocator.allocator_reserve_open)
    total_reserved = _state.sum_active_account_risk_reserved_loss_ccy(
        symbol=sym,
        include_pending=include_pending,
        include_open=include_open,
        family=fam,
    )
    rows = _state.list_active_account_risk_reservations(symbol=sym, family=fam)
    return AccountRiskReservationsStatusResponse(
        enabled=True,
        symbol=sym,
        active_count=len(rows),
        total_reserved_loss_ccy=float(total_reserved),
        rows=rows,
        include_pending=include_pending,
        include_open=include_open,
    )


@app.get(
    "/risk/account/reservations/status",
    response_model=AccountRiskReservationsStatusResponse,
)
async def get_account_reservations_status(
    symbol: str | None = None,
    family: str | None = None,
) -> AccountRiskReservationsStatusResponse:
    """Return active broker-neutral reservation totals and rows."""
    return await get_account_risk_reservations_status(symbol, family)


@app.post("/risk/account_risk/reservations/release")
async def release_account_risk_reservations_v2(req: AccountRiskReservationReleaseRequest) -> dict[str, Any]:
    """Release active account-risk reservations by reservation id, candidate uid, or broker pos id."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    if not any([req.reservation_id, req.candidate_uid, req.broker_pos_id]):
        raise HTTPException(
            status_code=422,
            detail="One of reservation_id, candidate_uid, or broker_pos_id is required",
        )
    released = _state.release_account_risk_reservation(
        reservation_id=req.reservation_id,
        candidate_uid=req.candidate_uid,
        broker_pos_id=req.broker_pos_id,
        symbol=req.symbol,
        family=req.family,
        reason=req.reason or "manual_release",
    )
    return {"ok": True, "released_count": int(released)}


@app.post("/risk/account/reservations/release")
async def release_account_risk_reservations(
    req: AccountRiskReservationReleaseRequest,
) -> dict[str, Any]:
    """Release active broker-neutral reservations by reservation id or broker position id."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    if not any([req.reservation_id, req.candidate_uid, req.broker_pos_id]):
        raise HTTPException(
            status_code=422,
            detail="One of reservation_id, candidate_uid, or broker_pos_id is required",
        )
    released = _state.release_risk_reservation(
        reservation_id=req.reservation_id,
        candidate_uid=req.candidate_uid,
        broker_pos_id=req.broker_pos_id,
        symbol=req.symbol,
        family=req.family,
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


@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest) -> PredictResponse:
    """Placeholder: no model is wired in yet.

    Returns an empty prediction/action list. The 7-step PredictionOrchestrator
    pipeline is re-enabled when boostlss_xs is wired into the runtime.
    """
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    return PredictResponse(predictions=[], actions=[])


@app.post("/trades/open")
async def open_trade(req: TradeOpenRequest):
    """Record an execution entry on the broker."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    run_id = _effective_run_id(req.run_id)
    _append_http_trace(
        endpoint="/trades/open",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
    )

    internal_id = _state.open_trade(
        symbol=req.symbol,
        candidate_uid=req.candidate_uid,
        broker_pos_id=req.broker_pos_id,
        side=req.side,
        entry_price=req.entry_price,
        entry_ts=req.entry_ts,
        horizon=req.horizon,
        reservation_id=req.reservation_id,
        run_id=run_id,
        family=req.family,
    )
    if _config.account_risk_enabled and (_account_risk_profile is not None):
        _state.promote_account_risk_reservation(
            broker_pos_id=req.broker_pos_id,
            reservation_id=req.reservation_id,
            candidate_uid=req.candidate_uid,
            symbol=req.symbol,
            family=req.family,
        )
    if _barrier_manager is not None:
        scans = _barrier_manager.find_holding_scans(req.symbol, req.candidate_uid)
        for scan in scans:
            if scan["broker_pos_id"] is None:
                _barrier_manager.set_broker_pos_id(scan["scan_id"], req.broker_pos_id)
                break
    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, family=req.family, status="OPEN").inc()
    out = {"status": "ok", "internal_trade_id": internal_id}
    _append_http_trace(
        endpoint="/trades/open",
        phase="response",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        response_payload=out,
        status_code=200,
    )
    return out


@app.get("/trades/active", response_model=list[ActiveTrade])
async def get_active_trades(symbol: str):
    """Fetch all OPEN trades for a symbol (used by cBot for recovery)."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    return _state.get_active_trades(symbol)


@app.get("/trades/summary")
async def get_trades_summary():
    """Return win/loss/pnl summary per symbol for closed trades."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    return _state.get_ledger_stats()


@app.get("/trades/open-summary")
async def get_open_positions_summary():
    """Cross-symbol view of all non-closed reservations with best-effort unrealized P&L."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    now = datetime.now(tz=timezone.utc)
    return _build_open_positions_summary(_state, now, _aggregators)


@app.get("/state/checkpoint")
async def checkpoint_state():
    """Force DuckDB to flush WAL to the on-disk database file."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    _state.checkpoint()
    return {"status": "ok", "checkpointed_at": datetime.now(tz=timezone.utc).isoformat()}


@app.post("/trades/touch")
async def touch_trade(req: TradeTouchRequest):
    """Record that a touch confirmation was processed for an open position."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    run_id = _effective_run_id(req.run_id)
    _append_http_trace(
        endpoint="/trades/touch",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
    )

    sym = req.symbol.upper()
    touch_bar_id = _state.get_latest_bar_id(sym)
    _state.touch_trade(req.broker_pos_id, touch_bar_id)
    out = {"status": "ok"}
    _append_http_trace(
        endpoint="/trades/touch",
        phase="response",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        response_payload=out,
        status_code=200,
    )
    return out


@app.post("/trades/update")
async def update_trade(req: TradeUpdateRequest):
    """Update a trade status (CLOSED/CANCELLED)."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    run_id = _effective_run_id(req.run_id)
    _append_http_trace(
        endpoint="/trades/update",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
    )

    _state.update_trade(
        broker_pos_id=req.broker_pos_id,
        status=req.status.value,
        exit_price=req.exit_price,
        exit_ts=req.exit_ts,
        pnl_pips=req.pnl_pips,
        run_id=run_id,
        symbol=req.symbol,
        close_reason=req.close_reason,
        commission_ccy=req.commission_ccy,
    )
    if _config.account_risk_enabled and (_account_risk_profile is not None) and req.status.value in {"CLOSED", "CANCELLED"}:
        _state.release_account_risk_reservation(
            broker_pos_id=req.broker_pos_id,
            reason=f"trade_{req.status.value.lower()}",
        )

    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, family=req.family, status=req.status.value).inc()
    if req.pnl_pips is not None:
        # Note: We need a way to look up the symbol from broker_pos_id if we want granular metrics here.
        # For now, we update a global or handle it in the background worker.
        pass

    out = {"status": "ok"}
    _append_http_trace(
        endpoint="/trades/update",
        phase="response",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        response_payload=out,
        status_code=200,
    )
    return out


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """System health: buffer depths (model-serving is a placeholder)."""
    if not _lifespan_ready:
        raise HTTPException(status_code=503, detail="Lifespan initialization in progress")
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    active_ticks = sorted(_aggregators.keys())
    bar_ticks: dict[str, list[int]] = {}
    bar_counts: dict[str, int] = {}
    for sym in _config.symbols:
        bar_ticks[sym] = list(active_ticks)
        bar_counts[sym] = _state.bar_count(sym, active_ticks[0]) if active_ticks else 0

    return HealthResponse(
        status="no_models",
        utc_now=datetime.now(tz=timezone.utc),
        models_loaded={},
        bar_ticks=bar_ticks,
        bar_counts=bar_counts,
        governance_dir="",
        model_cache_entries=0,
        governance_mode=str(_config.governance_mode).strip().lower(),
    )


@app.get("/status")
async def status() -> list[StatusSymbol]:
    """Per-symbol detailed status (degraded: no model/governance wired in)."""
    if _state is None:
        return []
    out: list[StatusSymbol] = []
    restart_report = _load_restart_reconciliation_report() or {}
    restart_verdict = str(restart_report.get("verdict", "")).strip() or None
    restart_reasons = [
        str(reason)
        for reason in restart_report.get("reasons", [])
        if str(reason).strip()
    ]
    METRIC_RESTART_VERDICT_ALLOWED.set(1.0 if restart_verdict == "ALLOW" else 0.0)
    active_ticks = sorted(_aggregators.keys())
    for sym in _config.symbols:
        out.append(StatusSymbol(
            symbol=sym,
            bar_ticks=list(active_ticks),
            bar_count=_state.bar_count(sym, active_ticks[0]) if active_ticks else 0,
            governance_dir="",
            model_loaded=False,
            model_month=None,
            has_threshold=False,
            deployment_state="placeholder",
            restart_verdict=restart_verdict,
            restart_reasons=list(restart_reasons),
            families=[],
        ))
    return out


@app.get("/runtime/feed/status", response_model=FeedStatusResponse)
async def runtime_feed_status() -> FeedStatusResponse:
    """Return per-symbol live feed ingest health and monotonicity counters."""
    symbols = sorted(set(_config.symbols) | set(_feed_state.keys()))
    rows: list[FeedStatusSymbol] = []
    for sym in symbols:
        st = _get_feed_tracker(sym)
        rows.append(
            FeedStatusSymbol(
                symbol=sym,
                total_received=int(st["total_received"]),
                total_accepted=int(st["total_accepted"]),
                total_dropped=int(st["total_dropped"]),
                total_batches=int(st["total_batches"]),
                duplicate_timestamps=int(st["duplicate_timestamps"]),
                monotonic_violations=int(st["monotonic_violations"]),
                duplicate_client_tick_seq=int(st["duplicate_client_tick_seq"]),
                client_seq_violations=int(st["client_seq_violations"]),
                symbol_tick_seq=int(st["symbol_tick_seq"]),
                last_client_tick_seq=(
                    int(st["last_client_tick_seq"])
                    if st.get("last_client_tick_seq") is not None
                    else None
                ),
                last_tick_ts_utc=st["last_tick_ts_utc"],
                last_ingest_utc=st["last_ingest_utc"],
                last_drop_reason=st["last_drop_reason"],
            )
        )
    return FeedStatusResponse(
        as_of_utc=datetime.now(tz=timezone.utc),
        governance_mode=str(_config.governance_mode).strip().lower(),
        record_raw_ticks=bool(_config.record_raw_ticks),
        symbols=rows,
    )


@app.post("/backfill", status_code=201)
async def backfill(req: BackfillRequest) -> dict:
    """Accept a batch of raw ticks, aggregate into bars, load into DuckDB.

    Called by the cBot on startup with ``MarketData.GetTicks()`` output.
    """
    if _state is None or not _aggregators:
        raise HTTPException(status_code=503, detail="Not initialized")
    run_id = _effective_run_id(req.run_id, *(t.run_id for t in req.ticks))
    _append_http_trace(
        endpoint="/backfill",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        extra={"tick_count": len(req.ticks), "bar_ticks": int(req.bar_ticks)},
    )

    bars = []
    for agg in _aggregators.values():
        bars.extend(agg.add_ticks(req.ticks))

    for bar in bars:
        _state.append_bar(bar)

    sym = req.symbol.upper()
    count = _state.bar_count(sym, req.bar_ticks)
    warmup_needed = max(_config.vol_window, _config.cost_window) + 1
    out = {
        "ok": True,
        "symbol": sym,
        "ticks_received": len(req.ticks),
        "bars_created": len(bars),
        "bar_count": count,
        "warm": count >= warmup_needed,
    }
    _append_http_trace(
        endpoint="/backfill",
        phase="response",
        run_id=run_id,
        symbol=sym,
        request_payload=req,
        response_payload=out,
        status_code=201,
    )
    return out


def _reject_tick(
    *,
    sym: str,
    feed: dict[str, Any],
    drop_reason: str,
    last_tick_ts_utc: datetime | None,
    run_id: str | None = None,
    tick: IncomingTick | None = None,
    endpoint: str = "/ticks",
) -> dict[str, Any]:
    feed["total_dropped"] = int(feed["total_dropped"]) + 1
    feed["last_drop_reason"] = str(drop_reason)
    out = {
        "ok": True,
        "symbol": sym,
        "tick_accepted": False,
        "drop_reason": str(drop_reason),
        "symbol_tick_seq": int(feed["symbol_tick_seq"]),
        "last_tick_ts_utc": last_tick_ts_utc,
        "last_client_tick_seq": (
            int(feed["last_client_tick_seq"])
            if feed.get("last_client_tick_seq") is not None
            else None
        ),
        "bar_completed": False,
        "completed_bar_ticks": [],
        "bar_count": _state.bar_count(sym, 100) if _state is not None else 0,
    }
    _append_http_trace(
        endpoint=endpoint,
        phase="tick_result",
        run_id=run_id,
        symbol=sym,
        request_payload=tick,
        response_payload=out,
        status_code=201,
        extra={"drop_reason": str(drop_reason), "last_tick_ts_utc": last_tick_ts_utc},
    )
    return out


def _ingest_tick_internal(tick: IncomingTick, *, endpoint: str = "/ticks") -> dict[str, Any]:
    """Ingest one tick with feed monotonicity checks and bar emission."""
    if _state is None or not _aggregators:
        raise HTTPException(status_code=503, detail="Not initialized")

    sym = tick.symbol.upper()
    tick_ts_utc = _as_utc_ts(tick.timestamp)
    now_utc = datetime.now(tz=timezone.utc)
    feed = _get_feed_tracker(sym)
    run_id = _effective_run_id(getattr(tick, "run_id", None))
    feed["total_received"] = int(feed["total_received"]) + 1
    feed["last_ingest_utc"] = now_utc

    client_tick_seq = tick.client_tick_seq
    client_seq_int: int | None = None
    if client_tick_seq is not None:
        try:
            client_seq_int = int(client_tick_seq)
        except Exception:
            client_seq_int = None
        if client_seq_int is not None:
            last_client_seq = feed.get("last_client_tick_seq")
            if last_client_seq is not None and client_seq_int <= int(last_client_seq):
                if client_seq_int == int(last_client_seq):
                    feed["duplicate_client_tick_seq"] = int(feed["duplicate_client_tick_seq"]) + 1
                    return _reject_tick(
                        sym=sym,
                        feed=feed,
                        drop_reason="duplicate_client_tick_seq",
                        last_tick_ts_utc=feed.get("last_tick_ts_utc"),
                        run_id=run_id,
                        tick=tick,
                        endpoint=endpoint,
                    )
                feed["client_seq_violations"] = int(feed["client_seq_violations"]) + 1
                return _reject_tick(
                    sym=sym,
                    feed=feed,
                    drop_reason="non_monotonic_client_tick_seq",
                    last_tick_ts_utc=feed.get("last_tick_ts_utc"),
                    run_id=run_id,
                    tick=tick,
                    endpoint=endpoint,
                )

    last_tick_ts = feed.get("last_tick_ts_utc")
    if isinstance(last_tick_ts, datetime) and tick_ts_utc <= last_tick_ts:
        # When client_tick_seq is present, use it as the canonical ingest order and
        # keep timestamp monotonicity counters informational-only.
        if client_seq_int is not None:
            if tick_ts_utc == last_tick_ts:
                feed["duplicate_timestamps"] = int(feed["duplicate_timestamps"]) + 1
            else:
                feed["monotonic_violations"] = int(feed["monotonic_violations"]) + 1
        else:
            if tick_ts_utc == last_tick_ts:
                feed["duplicate_timestamps"] = int(feed["duplicate_timestamps"]) + 1
                return _reject_tick(
                    sym=sym,
                    feed=feed,
                    drop_reason="duplicate_timestamp",
                    last_tick_ts_utc=last_tick_ts,
                    run_id=run_id,
                    tick=tick,
                    endpoint=endpoint,
                )
            feed["monotonic_violations"] = int(feed["monotonic_violations"]) + 1
            return _reject_tick(
                sym=sym,
                feed=feed,
                drop_reason="non_monotonic_timestamp",
                last_tick_ts_utc=last_tick_ts,
                run_id=run_id,
                tick=tick,
                endpoint=endpoint,
            )

    if _config.record_raw_ticks:
        source = "live"
        _state.record_raw_tick(tick, source=source)

    completed_bar_ticks = []
    bars = []
    for agg in _aggregators.values():
        bars.extend(agg.add_ticks([tick]))

    bar_completed = False
    for bar in bars:
        _state.append_bar(bar)
        completed_bar_ticks.append(bar.bar_ticks)
        bar_completed = True

    feed["total_accepted"] = int(feed["total_accepted"]) + 1
    feed["symbol_tick_seq"] = int(feed["symbol_tick_seq"]) + 1
    if isinstance(last_tick_ts, datetime):
        feed["last_tick_ts_utc"] = tick_ts_utc if tick_ts_utc > last_tick_ts else last_tick_ts
    else:
        feed["last_tick_ts_utc"] = tick_ts_utc
    if client_seq_int is not None:
        feed["last_client_tick_seq"] = int(client_seq_int)
    feed["last_drop_reason"] = None
    out = {
        "ok": True,
        "symbol": sym,
        "tick_accepted": True,
        "drop_reason": None,
        "symbol_tick_seq": int(feed["symbol_tick_seq"]),
        "last_tick_ts_utc": feed.get("last_tick_ts_utc"),
        "last_client_tick_seq": (
            int(feed["last_client_tick_seq"])
            if feed.get("last_client_tick_seq") is not None
            else None
        ),
        "bar_completed": bar_completed,
        "completed_bar_ticks": completed_bar_ticks,
        "bar_count": _state.bar_count(sym, 100),  # Return standard 100-tick count as baseline
    }
    _append_http_trace(
        endpoint=endpoint,
        phase="tick_result",
        run_id=run_id,
        symbol=sym,
        request_payload=tick,
        response_payload=out,
        status_code=201,
        extra={"tick_ts_utc": tick_ts_utc},
    )
    return out


@app.post("/ticks", status_code=201)
async def ingest_tick(tick: IncomingTick) -> dict:
    """Accept a single live tick, buffer it, and auto-emit bars.

    Called by the cBot on each ``OnTick()`` event.
    """
    _append_http_trace(
        endpoint="/ticks",
        phase="request",
        run_id=_effective_run_id(tick.run_id),
        symbol=tick.symbol,
        request_payload=tick,
    )
    out = _ingest_tick_internal(tick, endpoint="/ticks")
    _append_http_trace(
        endpoint="/ticks",
        phase="response",
        run_id=_effective_run_id(tick.run_id),
        symbol=tick.symbol,
        request_payload=tick,
        response_payload=out,
        status_code=201,
    )
    return out


@app.post("/ticks/batch", status_code=201)
async def ingest_ticks_batch(req: TickBatchRequest) -> dict:
    """Accept a batch of live ticks for lower-overhead ingest."""
    if _state is None or not _aggregators:
        raise HTTPException(status_code=503, detail="Not initialized")
    if not req.ticks:
        raise HTTPException(status_code=422, detail="ticks must be non-empty")
    run_id = _effective_run_id(req.run_id, *(t.run_id for t in req.ticks))
    _append_http_trace(
        endpoint="/ticks/batch",
        phase="request",
        run_id=run_id,
        symbol=req.symbol,
        request_payload=req,
        extra={"tick_count": len(req.ticks)},
    )

    symbols_seen = {str(t.symbol).upper().strip() for t in req.ticks if str(t.symbol).strip() != ""}
    if not symbols_seen:
        raise HTTPException(status_code=422, detail="ticks must include symbol")
    if req.symbol is not None and str(req.symbol).strip() != "":
        req_sym = str(req.symbol).upper().strip()
        if symbols_seen != {req_sym}:
            raise HTTPException(
                status_code=422,
                detail=f"Batch symbol mismatch: request symbol={req_sym} tick_symbols={sorted(symbols_seen)}",
            )
        batch_sym = req_sym
    else:
        if len(symbols_seen) != 1:
            raise HTTPException(
                status_code=422,
                detail=f"ticks must contain exactly one symbol per batch; got={sorted(symbols_seen)}",
            )
        batch_sym = next(iter(symbols_seen))

    feed = _get_feed_tracker(batch_sym)
    feed["total_batches"] = int(feed["total_batches"]) + 1

    accepted = 0
    dropped = 0
    completed_bar_ticks: list[int] = []
    for tick in req.ticks:
        out = _ingest_tick_internal(tick, endpoint="/ticks/batch")
        if bool(out.get("tick_accepted", False)):
            accepted += 1
        else:
            dropped += 1
        if bool(out.get("bar_completed", False)):
            completed_bar_ticks.extend([int(x) for x in out.get("completed_bar_ticks", [])])

    out = {
        "ok": True,
        "symbol": batch_sym,
        "ticks_received": len(req.ticks),
        "accepted_count": int(accepted),
        "dropped_count": int(dropped),
        "bar_completed": len(completed_bar_ticks) > 0,
        "completed_bar_ticks": completed_bar_ticks,
        "symbol_tick_seq": int(feed["symbol_tick_seq"]),
        "last_tick_ts_utc": feed.get("last_tick_ts_utc"),
        "last_client_tick_seq": (
            int(feed["last_client_tick_seq"])
            if feed.get("last_client_tick_seq") is not None
            else None
        ),
        "bar_count": _state.bar_count(batch_sym, 100),
    }
    _append_http_trace(
        endpoint="/ticks/batch",
        phase="response",
        run_id=run_id,
        symbol=batch_sym,
        request_payload=req,
        response_payload=out,
        status_code=201,
    )
    return out
