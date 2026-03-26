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
from bisect import bisect_left
import hashlib
import json
import logging
import math
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field, model_validator

from src.behemoth.api.dashboard import router as dashboard_router
from src.behemoth.core.features import (
    FeatureConfig,
    compute_feature_matrix_from_bars,
    compute_features_from_bars,
    pip_size,
)
from src.behemoth.core.historical_governance_validation import (
    failed_checks,
    summarize_failures,
    validate_historical_governance,
)
from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
from src.behemoth.core.registry import CandidateRegistry
from src.behemoth.core.schemas import (
    ActiveTrade,
    AccountRiskSnapshotRequest,
    IncomingTick,
    IncomingTickBar,
    ModelFeatures,
    OcoPrediction,
    TradeOpenRequest,
    TradeTouchRequest,
    TradeUpdateRequest,
)
from src.behemoth.risk.account import (
    AccountRiskProfile,
    evaluate_account_risk_limits,
    evaluate_trade_risk_guard,
    load_account_risk_profile,
    trading_day_id,
)
from src.behemoth.runtime.state import StateManager
from src.behemoth.runtime.tick_aggregator import TickAggregator

evaluate_account_limits = evaluate_account_risk_limits
evaluate_trade_guard = evaluate_trade_risk_guard

logger = logging.getLogger("behemoth.api")

# ── App ───────────────────────────────────────────────────────────────

# ── Global State ──────────────────────────────────────────────────────

_state: StateManager | None = None
_aggregators: dict[int, TickAggregator] = {}
_registry: CandidateRegistry | None = None
_historical_registry: HistoricalCandidateRegistry | None = None
_models: dict[str, object] = {}          # cache key -> loaded CatBoostClassifier
_thresholds: dict[str, dict] = {}        # cache key -> threshold config
_model_months: dict[str, str] = {}       # cache key -> "2025-12"
_historical_prediction_universes: dict[str, dict[datetime, set[str]]] = {}
_historical_prediction_candidate_index: dict[str, dict[str, list[datetime]]] = {}
_historical_prediction_candidate_ordinal_index: dict[str, dict[str, list[int]]] = {}
_historical_prediction_candidate_cursor: dict[str, dict[str, int]] = {}
_historical_prediction_payload_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
_historical_prediction_payload_cursor: dict[str, dict[str, int]] = {}
_models_dir: Path = Path("models/oco")
_account_risk_rules_path: Path = Path("configs/research/governance/account_risk/account_risk_rules.yaml")
_account_risk_profile: AccountRiskProfile | None = None
_historical_entries_loaded: int = 0
_historical_preflight_failed_checks: int = 0
_historical_preflight_summary: str = ""
_feed_state: dict[str, dict[str, Any]] = {}
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_HISTORICAL_PREDICTION_TOLERANCE_SEC = 30.0


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
    "Total account-risk blocked execution intents",
    ["symbol", "reason"],
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
    ["symbol", "reason"],
)

METRIC_ACCOUNT_RISK_ALLOCATOR_ADMITTED_TOTAL = Counter(
    "behemoth_account_risk_allocator_admitted_total",
    "Total account risk allocator-admitted candidates",
    ["symbol"],
)


class AppConfig(BaseModel):
    """Runtime configuration for the inference server."""
    vol_window: int = 96
    cost_window: int = 288
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
                (
                    "tolerant"
                    if str(os.getenv("BEHEMOTH_GOVERNANCE_MODE", "live")).strip().lower()
                    in {"historical", "historical_auto"}
                    else "exact"
                ),
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
        default_factory=lambda: str(os.getenv("BEHEMOTH_RECORD_RAW_TICKS", "false")).strip().lower()
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


def _is_historical_mode() -> bool:
    return str(_config.governance_mode).strip().lower() in {
        "historical",
        "historical_auto",
    }


def _cache_key(symbol: str, model_month: str | None = None) -> str:
    sym = str(symbol).upper().strip()
    if _is_historical_mode() and model_month:
        return f"{sym}|{str(model_month).strip()}"
    return sym


def _has_loaded_model_for_symbol(symbol: str) -> bool:
    sym = str(symbol).upper().strip()
    if sym in _models:
        return True
    pref = f"{sym}|"
    return any(k.startswith(pref) for k in _models)


def _latest_loaded_month_for_symbol(symbol: str) -> str | None:
    sym = str(symbol).upper().strip()
    if sym in _model_months:
        return _model_months.get(sym)
    pref = f"{sym}|"
    months = [m for k, m in _model_months.items() if k.startswith(pref)]
    if not months:
        return None
    return sorted(months)[-1]


def _run_historical_preflight(history_dir: Path) -> None:
    global _historical_preflight_failed_checks, _historical_preflight_summary
    checks = validate_historical_governance(
        history_dir,
        required_symbols=[str(s).upper().strip() for s in _config.symbols],
    )
    bad = failed_checks(checks)
    _historical_preflight_failed_checks = len(bad)
    _historical_preflight_summary = summarize_failures(checks, limit=10)
    if bad:
        mode = str(_config.historical_preflight_mode).strip().lower()
        if mode not in {"warn", "warning", "ignore", "off"}:
            raise RuntimeError(
                "Historical governance preflight failed: "
                f"failed_checks={len(bad)} { _historical_preflight_summary }"
            )
        logger.warning(
            "Historical governance preflight failed but was downgraded by "
            "BEHEMOTH_HISTORICAL_PREFLIGHT_MODE=%s: failed_checks=%d %s",
            mode,
            len(bad),
            _historical_preflight_summary,
        )
        return
    logger.info(
        "Historical governance preflight passed: checks=%d history_dir=%s",
        len(checks),
        history_dir,
    )


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event."""
    global _state, _aggregators, _registry, _historical_registry, _feed_state
    global _models_dir, _account_risk_rules_path, _account_risk_profile
    global _historical_entries_loaded, _historical_preflight_failed_checks, _historical_preflight_summary
    global _historical_prediction_universes, _historical_prediction_candidate_index
    global _historical_prediction_candidate_ordinal_index
    global _historical_prediction_candidate_cursor, _historical_prediction_payload_rows
    global _historical_prediction_payload_cursor

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
    _feed_state = {}
    try:
        _aggregators = {}
        _historical_prediction_universes = {}
        _historical_prediction_candidate_index = {}
        _historical_prediction_candidate_ordinal_index = {}
        _historical_prediction_candidate_cursor = {}
        _historical_prediction_payload_rows = {}
        _historical_prediction_payload_cursor = {}
        if _is_historical_mode():
            hist_dir = Path(str(_config.governance_history_dir))
            _historical_registry = HistoricalCandidateRegistry.load(hist_dir)
            _run_historical_preflight(hist_dir)
            _registry = None
            _historical_entries_loaded = len(_historical_registry._entries)
            logger.info(
                "Loaded %d month-scoped historical lock entries from %s",
                _historical_entries_loaded,
                hist_dir,
            )
            unique_bar_ticks = {int(c.bar_ticks) for c in _historical_registry.all_candidates()}
        else:
            _registry = CandidateRegistry.load(
                os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco"),
                models_dir=Path(_config.models_dir),
            )
            _historical_registry = None
            _historical_entries_loaded = 0
            _historical_preflight_failed_checks = 0
            _historical_preflight_summary = ""
            logger.info("Loaded %d candidates from governance locks", len(_registry.all_candidates()))
            unique_bar_ticks = {int(c.bar_ticks) for c in _registry.all_candidates()}

        if not unique_bar_ticks:
            unique_bar_ticks = {100}
        for bt in unique_bar_ticks:
            _aggregators[bt] = TickAggregator(bar_ticks=bt)
            logger.info("Initialized TickAggregator for %d ticks", bt)

    except FileNotFoundError:
        _registry = None
        _historical_registry = None
        _historical_entries_loaded = 0
        _historical_preflight_failed_checks = 0
        _historical_preflight_summary = ""
        _aggregators = {100: TickAggregator(bar_ticks=100)}
        logger.warning(
            "Governance lock source not found — using empty registry and default 100-tick aggregator"
        )
    _models_dir = Path(_config.models_dir)
    _load_models()
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


app = FastAPI(
    title="Behemoth OCO Inference API",
    version="0.1.0",
    description="Production inference server for the tick-based OCO stop-limit strategy.",
    lifespan=lifespan,
)

app.include_router(dashboard_router)


def _catboost_cls() -> Any | None:
    try:
        from catboost import CatBoostClassifier
    except ImportError:
        logger.error("CatBoost not installed — predictions will be unavailable.")
        return None
    return CatBoostClassifier


def _load_model_binding_into_cache(
    *,
    symbol: str,
    binding: dict[str, Any],
    cache_key: str,
    expected_month: str | None,
) -> tuple[bool, str]:
    cb_cls = _catboost_cls()
    if cb_cls is None:
        return False, "catboost_unavailable"

    model_path = Path(str(binding.get("model_cbm_path", "")))
    thr_path = Path(str(binding.get("model_threshold_json_path", "")))
    exp_model_sha = str(binding.get("model_cbm_sha256", "")).strip()
    exp_thr_sha = str(binding.get("model_threshold_json_sha256", "")).strip()
    lock_month = str(binding.get("model_month", "")).strip()

    if (not model_path.exists()) or (not thr_path.exists()):
        logger.error(
            "Locked artifacts missing for %s: model=%s threshold=%s",
            symbol,
            model_path,
            thr_path,
        )
        return False, "artifact_missing"

    got_model_sha = _sha256(model_path)
    got_thr_sha = _sha256(thr_path)
    if (got_model_sha != exp_model_sha) or (got_thr_sha != exp_thr_sha):
        logger.error("Locked artifact hash mismatch for %s — refusing model load.", symbol)
        return False, "artifact_hash_mismatch"

    month = model_path.stem.split("_")[-1]
    if lock_month and (month != lock_month):
        logger.error(
            "Locked model month mismatch for %s: lock=%s file=%s",
            symbol,
            lock_month,
            month,
        )
        return False, "lock_month_mismatch"
    if expected_month and month != expected_month:
        logger.error(
            "Expected model month mismatch for %s: expected=%s file=%s",
            symbol,
            expected_month,
            month,
        )
        return False, "expected_month_mismatch"

    model = cb_cls()
    model.load_model(str(model_path))
    thr_cfg = json.loads(thr_path.read_text())
    thr_month = str(thr_cfg.get("model_month", "")).strip()
    if thr_month and thr_month != month:
        logger.error(
            "Threshold JSON model month mismatch for %s: model=%s threshold=%s",
            symbol,
            month,
            thr_month,
        )
        return False, "threshold_month_mismatch"
    _models[cache_key] = model
    _model_months[cache_key] = month
    _thresholds[cache_key] = thr_cfg
    logger.info("Loaded lock-bound model for %s (month %s): %s", symbol, month, model_path.name)
    return True, month


def _load_models() -> None:
    """Load model cache according to governance mode."""
    global _models, _thresholds, _model_months
    _models = {}
    _thresholds = {}
    _model_months = {}
    if not _models_dir.exists():
        logger.warning("Models directory %s does not exist yet.", _models_dir)
        return

    if _is_historical_mode():
        # Historical mode uses lazy per-(symbol,month) loading on /predict.
        logger.info("Historical governance mode enabled: model cache is lazy-loaded by month.")
        return

    if _registry is None:
        logger.error(
            "Governance registry unavailable — refusing to load models without lock binding."
        )
        return

    for sym in _config.symbols:
        binding = _registry.get_model_binding(sym)
        if not binding:
            logger.error("No governance model binding for %s — skipping model load.", sym)
            continue
        cache_key = _cache_key(sym)
        _load_model_binding_into_cache(
            symbol=sym,
            binding=binding,
            cache_key=cache_key,
            expected_month=str(binding.get("model_month", "")).strip() or None,
        )

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
    row = _state._con.execute(
        """
        SELECT close_price, close_ts
        FROM tick_bars
        WHERE symbol = ?
        ORDER BY row_id DESC
        LIMIT 1
        """,
        [sym.upper()],
    ).fetchone()
    if not row or row[0] is None:
        return None
    close_ts = row[1]
    if isinstance(close_ts, datetime):
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        else:
            close_ts = close_ts.astimezone(timezone.utc)
    return {
        "symbol": sym.upper(),
        "price": float(row[0]),
        "close_ts": close_ts,
    }


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


def _normalize_completed_bar_ticks(raw: list[int] | None) -> set[int]:
    """Normalize client-provided completed bar-tick identifiers."""
    out: set[int] = set()
    if not raw:
        return out
    for v in raw:
        try:
            iv = int(v)
        except Exception:
            continue
        if iv > 0:
            out.add(iv)
    return out


def _candidate_regime_name(cand: Any) -> str:
    txt = str(getattr(cand, "regime_desc", "") or "").strip()
    if txt and txt.lower() not in {"nan", "none"}:
        return txt.split(";")[0].strip().lower()
    sid = str(getattr(cand, "candidate_uid", "") or "").strip()
    parts = sid.split("__")
    if len(parts) >= 3:
        return "__".join(parts[1:-1]).strip().lower()
    return "all"


def _regime_cmp(value: float, threshold: float, *, op: str) -> bool:
    if not (math.isfinite(float(value)) and math.isfinite(float(threshold))):
        return True
    if op == "<=":
        return float(value) <= float(threshold)
    if op == ">=":
        return float(value) >= float(threshold)
    return True


def _regime_is_active(
    regime_name: str,
    *,
    features: ModelFeatures,
    close_ts_utc: datetime,
    regime_q: dict[str, float] | None,
) -> bool:
    r = str(regime_name or "").strip().lower()
    q = regime_q or {}
    if r in {"", "all"}:
        return True
    if "_and_" in r:
        return all(
            _regime_is_active(
                sub,
                features=features,
                close_ts_utc=close_ts_utc,
                regime_q=q,
            )
            for sub in r.split("_and_")
        )

    h = int(close_ts_utc.hour)
    if r == "london":
        return h in {7, 8, 9, 10, 11}
    if r == "ny_overlap":
        return h in {13, 14, 15, 16}
    if r == "asia":
        return h in {0, 1, 2, 3, 4, 5}
    if r == "low_cost_q30":
        return _regime_cmp(float(features.cost_est_pips), float(q.get("cost_q30", float("nan"))), op="<=")
    if r == "low_cost_q50":
        return _regime_cmp(float(features.cost_est_pips), float(q.get("cost_q50", float("nan"))), op="<=")
    if r == "high_range_q70":
        return _regime_cmp(float(features.range_pips), float(q.get("rng_q70", float("nan"))), op=">=")
    if r == "high_range_q80":
        return _regime_cmp(float(features.range_pips), float(q.get("rng_q80", float("nan"))), op=">=")
    if r == "high_abs_vel_q70":
        return _regime_cmp(
            float(features.vel_abs_cost_units_h1),
            float(q.get("vel_q70", float("nan"))),
            op=">=",
        )
    if r == "high_abs_vel_q80":
        return _regime_cmp(
            float(features.vel_abs_cost_units_h1),
            float(q.get("vel_q80", float("nan"))),
            op=">=",
        )
    # Unknown regime token: keep permissive for forward compatibility.
    return True


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
    threshold_blocked: bool = False
    threshold_block_reason: str | None = None
    risk_rank_score: float | None = None
    risk_reserved: bool = False
    risk_reserved_amount_ccy: float | None = None
    risk_headroom_after_ccy: float | None = None
    risk_reservation_id: str | None = None


@dataclass
class _ResolvedRuntimeContract:
    symbol: str
    model_month: str
    cache_key: str
    candidates: list[Any]
    model_binding: dict[str, Any]
    cap_pips: float
    source: str
    lock_path: str | None = None


def _normalize_model_month(raw: str | None) -> str | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    if len(txt) == 6 and txt.isdigit():
        txt = f"{txt[:4]}-{txt[4:]}"
    if _MONTH_RE.match(txt):
        return txt
    return None


def _month_from_close_ts(ts: datetime) -> str:
    v = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m")


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


def _trace_predict_response(
    *,
    req: PredictRequest,
    sym: str,
    run_id: str | None,
    results: list[Any],
    reason: str,
    close_ts: datetime | None = None,
    completed_ticks: list[int] | None = None,
    candidate_count_before_gate: int | None = None,
    candidate_count_after_completed_ticks: int | None = None,
    candidate_count_after_universe_gate: int | None = None,
    candidate_trace_rows: list[dict[str, Any]] | None = None,
) -> list[Any]:
    selected_count = 0
    risk_blocked_count = 0
    try:
        for row in results:
            selected_count += int(getattr(row, "selected_exec", 0) == 1)
            risk_blocked_count += int(bool(getattr(row, "risk_blocked", False)))
    except Exception:
        pass
    _append_http_trace(
        endpoint="/predict",
        phase="response",
        run_id=run_id,
        symbol=sym,
        request_payload=req,
        response_payload=results,
        status_code=200,
        extra={
            "reason": reason,
            "close_ts": close_ts,
            "completed_bar_ticks": completed_ticks or [],
            "result_count": len(results),
            "selected_count": int(selected_count),
            "risk_blocked_count": int(risk_blocked_count),
            "candidate_count_before_gate": candidate_count_before_gate,
            "candidate_count_after_completed_ticks": candidate_count_after_completed_ticks,
            "candidate_count_after_universe_gate": candidate_count_after_universe_gate,
            "candidate_trace_rows": candidate_trace_rows or [],
        },
    )
    return results


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


def _resolve_missing_historical_month(symbol: str, requested_month: str) -> str | None:
    if _historical_registry is None:
        return None
    months = _historical_registry.months_for_symbol(symbol)
    if not months:
        return None
    policy = str(_config.governance_missing_month_policy).strip().lower()
    if policy in {"latest", "latest_available"}:
        return months[-1]
    if policy in {"nearest_previous", "previous", "floor"}:
        prior = [m for m in months if m <= requested_month]
        return prior[-1] if prior else None
    return None


def _resolve_runtime_contract(sym: str, close_ts: datetime) -> _ResolvedRuntimeContract:
    symbol = str(sym).upper().strip()

    if _is_historical_mode():
        if _historical_registry is None:
            raise HTTPException(status_code=503, detail="Historical governance registry not loaded")

        forced_month = _normalize_model_month(_config.force_model_month)
        if _config.force_model_month and forced_month is None:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid BEHEMOTH_FORCE_MODEL_MONTH={_config.force_model_month!r}; expected YYYY-MM",
            )
        requested_month = forced_month or _month_from_close_ts(close_ts)
        entry = _historical_registry.get_entry(symbol, requested_month)
        resolved_month = requested_month
        if entry is None:
            fallback_month = _resolve_missing_historical_month(symbol, requested_month)
            if fallback_month is not None:
                entry = _historical_registry.get_entry(symbol, fallback_month)
                resolved_month = fallback_month

        if entry is None:
            available = _historical_registry.months_for_symbol(symbol)
            avail_txt = ",".join(available) if available else "<none>"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No historical lock for {symbol} month {requested_month} "
                    f"(policy={_config.governance_missing_month_policy}). "
                    f"available_months={avail_txt}"
                ),
            )

        model_binding = dict(entry.model_binding)
        return _ResolvedRuntimeContract(
            symbol=symbol,
            model_month=resolved_month,
            cache_key=_cache_key(symbol, resolved_month),
            candidates=list(entry.candidates),
            model_binding=model_binding,
            cap_pips=float(entry.cap_pips),
            source="historical",
            lock_path=str(entry.lock_path),
        )

    if _registry is None:
        raise HTTPException(status_code=503, detail="Candidate registry not loaded")

    model_binding = _registry.get_model_binding(symbol)
    if not model_binding:
        raise HTTPException(status_code=503, detail=f"No model binding registered for {symbol}")
    model_month = (
        _normalize_model_month(str(model_binding.get("model_month", "")).strip())
        or "unknown"
    )
    return _ResolvedRuntimeContract(
        symbol=symbol,
        model_month=model_month,
        cache_key=_cache_key(symbol),
        candidates=_registry.get_candidates(symbol),
        model_binding=dict(model_binding),
        cap_pips=float(_registry.get_cap_pips(symbol)),
        source="live",
        lock_path=None,
    )


def _ensure_model_and_threshold(contract: _ResolvedRuntimeContract) -> tuple[Any, dict[str, Any]]:
    model = _models.get(contract.cache_key)
    thr_cfg = _thresholds.get(contract.cache_key)
    if model is not None and isinstance(thr_cfg, dict):
        return model, thr_cfg

    ok, reason = _load_model_binding_into_cache(
        symbol=contract.symbol,
        binding=contract.model_binding,
        cache_key=contract.cache_key,
        expected_month=(contract.model_month if contract.model_month != "unknown" else None),
    )
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to load lock-bound model for {contract.symbol}: {reason}",
        )
    model = _models.get(contract.cache_key)
    thr_cfg = _thresholds.get(contract.cache_key)
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"No CatBoost model loaded for {contract.symbol} (cache={contract.cache_key})",
        )
    return model, thr_cfg if isinstance(thr_cfg, dict) else {}


def _load_historical_prediction_universe(contract: _ResolvedRuntimeContract) -> dict[datetime, set[str]]:
    """Load the locked historical prediction row-universe for exact replay parity."""
    if not _is_historical_mode():
        return {}
    cached = _historical_prediction_universes.get(contract.cache_key)
    if cached is not None:
        return cached

    override_path = str(os.getenv("BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE", "")).strip()
    pred_path = (
        Path(override_path)
        if override_path
        else Path(str(contract.model_binding.get("predictions_path", "")).strip())
    )
    if not pred_path.exists():
        _historical_prediction_universes[contract.cache_key] = {}
        return {}

    try:
        import duckdb
    except Exception:
        _historical_prediction_universes[contract.cache_key] = {}
        return {}

    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT
                try_cast(close_ts AS TIMESTAMP WITH TIME ZONE) AS close_ts,
                candidate_uid
            FROM read_parquet(?)
            WHERE test_month = ?
              AND upper(split_part(candidate_uid, '|', 2)) = ?
            ORDER BY close_ts
            """,
            [
                str(pred_path),
                str(contract.model_month),
                str(contract.symbol).upper().strip(),
            ],
        ).fetchall()
    finally:
        con.close()

    out: dict[datetime, set[str]] = {}
    for close_ts, candidate_uid in rows:
        if close_ts is None:
            continue
        ts_utc = _as_utc_ts(close_ts)
        uid = str(candidate_uid or "").strip()
        if not uid:
            continue
        bucket = out.setdefault(ts_utc, set())
        bucket.add(uid)
    _historical_prediction_universes[contract.cache_key] = out
    return out


def _load_historical_prediction_candidate_index(
    contract: _ResolvedRuntimeContract,
) -> dict[str, list[datetime]]:
    """Load per-candidate locked prediction timestamps for tolerant replay gating."""
    if not _is_historical_mode():
        return {}
    cached = _historical_prediction_candidate_index.get(contract.cache_key)
    if cached is not None:
        return cached

    override_path = str(os.getenv("BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE", "")).strip()
    pred_path = (
        Path(override_path)
        if override_path
        else Path(str(contract.model_binding.get("predictions_path", "")).strip())
    )
    if not pred_path.exists():
        _historical_prediction_candidate_index[contract.cache_key] = {}
        return {}

    try:
        import duckdb
    except Exception:
        _historical_prediction_candidate_index[contract.cache_key] = {}
        return {}

    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT
                try_cast(close_ts AS TIMESTAMP WITH TIME ZONE) AS close_ts,
                candidate_uid
            FROM read_parquet(?)
            WHERE test_month = ?
              AND upper(split_part(candidate_uid, '|', 2)) = ?
            ORDER BY candidate_uid, close_ts
            """,
            [
                str(pred_path),
                str(contract.model_month),
                str(contract.symbol).upper().strip(),
            ],
        ).fetchall()
    finally:
        con.close()

    out: dict[str, list[datetime]] = {}
    for close_ts, candidate_uid in rows:
        if close_ts is None:
            continue
        uid = str(candidate_uid or "").strip()
        if not uid:
            continue
        out.setdefault(uid, []).append(_as_utc_ts(close_ts))
    _historical_prediction_candidate_index[contract.cache_key] = out
    return out


def _load_historical_prediction_candidate_ordinal_index(
    contract: _ResolvedRuntimeContract,
) -> dict[str, list[int]]:
    """Load per-candidate 0-indexed bar ordinals for ordinal-mode replay gating.

    Ordinals are computed with DENSE_RANK() over all distinct close_ts values
    for each bar_ticks granularity within the test_month.  Bar ordinal 0 is the
    first bar close that appears in the parquet for that (symbol, bar_ticks) pair.

    Both the server and the JForex adapter count from 0 at session start, so
    candidate N fires when the adapter has closed its Nth bar (±ordinal tolerance).
    """
    if not _is_historical_mode():
        return {}
    cached = _historical_prediction_candidate_ordinal_index.get(contract.cache_key)
    if cached is not None:
        return cached

    override_path = str(os.getenv("BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE", "")).strip()
    pred_path = (
        Path(override_path)
        if override_path
        else Path(str(contract.model_binding.get("predictions_path", "")).strip())
    )
    if not pred_path.exists():
        _historical_prediction_candidate_ordinal_index[contract.cache_key] = {}
        return {}

    try:
        import duckdb
    except Exception:
        _historical_prediction_candidate_ordinal_index[contract.cache_key] = {}
        return {}

    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT
                (DENSE_RANK() OVER (
                    PARTITION BY try_cast(split_part(candidate_uid, '|', 3) AS INTEGER)
                    ORDER BY try_cast(close_ts AS TIMESTAMP WITH TIME ZONE)
                ) - 1)::INTEGER AS bar_ordinal,
                candidate_uid
            FROM read_parquet(?)
            WHERE test_month = ?
              AND upper(split_part(candidate_uid, '|', 2)) = ?
            ORDER BY candidate_uid, bar_ordinal
            """,
            [
                str(pred_path),
                str(contract.model_month),
                str(contract.symbol).upper().strip(),
            ],
        ).fetchall()
    finally:
        con.close()

    out: dict[str, list[int]] = {}
    for bar_ordinal, candidate_uid in rows:
        if bar_ordinal is None:
            continue
        uid = str(candidate_uid or "").strip()
        if not uid:
            continue
        out.setdefault(uid, []).append(int(bar_ordinal))
    _historical_prediction_candidate_ordinal_index[contract.cache_key] = out
    return out


def _load_historical_prediction_payload_rows(
    contract: _ResolvedRuntimeContract,
) -> dict[str, list[dict[str, Any]]]:
    """Load locked historical prediction payload rows for replay parity."""
    if not _is_historical_mode():
        return {}
    cached = _historical_prediction_payload_rows.get(contract.cache_key)
    if cached is not None:
        return cached

    override_path = str(os.getenv("BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE", "")).strip()
    pred_path = (
        Path(override_path)
        if override_path
        else Path(str(contract.model_binding.get("predictions_path", "")).strip())
    )
    if not pred_path.exists():
        _historical_prediction_payload_rows[contract.cache_key] = {}
        return {}

    try:
        import duckdb
    except Exception:
        _historical_prediction_payload_rows[contract.cache_key] = {}
        return {}

    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT
                try_cast(close_ts AS TIMESTAMP WITH TIME ZONE) AS close_ts,
                candidate_uid,
                try_cast(pred_prob AS DOUBLE) AS pred_prob,
                try_cast(threshold_exec AS DOUBLE) AS threshold_exec,
                try_cast(selected_exec AS INTEGER) AS selected_exec
            FROM read_parquet(?)
            WHERE test_month = ?
              AND upper(split_part(candidate_uid, '|', 2)) = ?
            ORDER BY candidate_uid, close_ts
            """,
            [
                str(pred_path),
                str(contract.model_month),
                str(contract.symbol).upper().strip(),
            ],
        ).fetchall()
    finally:
        con.close()

    out: dict[str, list[dict[str, Any]]] = {}
    for close_ts, candidate_uid, pred_prob, threshold_exec, selected_exec in rows:
        if close_ts is None:
            continue
        uid = str(candidate_uid or "").strip()
        if not uid:
            continue
        out.setdefault(uid, []).append(
            {
                "close_ts": _as_utc_ts(close_ts),
                "pred_prob": float(pred_prob) if pred_prob is not None else None,
                "threshold_exec": float(threshold_exec) if threshold_exec is not None else None,
                "selected_exec": int(selected_exec or 0),
            }
        )
    _historical_prediction_payload_rows[contract.cache_key] = out
    return out


def _resolve_historical_prediction_payload_overrides(
    *,
    contract: _ResolvedRuntimeContract,
    close_ts: datetime,
    candidates: list[Any],
) -> dict[str, dict[str, Any]]:
    """Resolve nearest locked prediction payload rows for the current close timestamp."""
    if not _is_historical_mode():
        return {}
    mode = str(_config.historical_prediction_payload_mode).strip().lower()
    if mode not in {"locked", "parquet", "override"}:
        return {}

    rows_by_uid = _load_historical_prediction_payload_rows(contract)
    if not rows_by_uid:
        return {}

    close_ts_utc = _as_utc_ts(close_ts)
    tolerance = timedelta(seconds=float(_config.historical_prediction_tolerance_sec))
    cursor_by_uid = _historical_prediction_payload_cursor.setdefault(contract.cache_key, {})
    out: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        canonical_uid = (
            f"oco|{contract.symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        )
        rows = rows_by_uid.get(canonical_uid, [])
        if not rows:
            continue
        cursor = int(cursor_by_uid.get(canonical_uid, 0))
        while cursor < len(rows):
            row_ts = _as_utc_ts(rows[cursor]["close_ts"])
            if row_ts >= close_ts_utc - tolerance:
                break
            cursor += 1
        choices: list[tuple[timedelta, datetime, int, dict[str, Any]]] = []
        for idx in range(cursor, len(rows)):
            row = rows[idx]
            row_ts = _as_utc_ts(row["close_ts"])
            if row_ts > close_ts_utc + tolerance:
                break
            delta = abs(close_ts_utc - row_ts)
            if delta <= tolerance:
                choices.append((delta, row_ts, idx, row))
        if not choices:
            cursor_by_uid[canonical_uid] = cursor
            continue
        selected_choices = [item for item in choices if int(item[3].get("selected_exec") or 0) == 1]
        if selected_choices:
            choices = selected_choices
        choices.sort(key=lambda item: (item[0], item[1], item[2]))
        best_delta = choices[0][0]
        if sum(1 for delta, _, _, _ in choices if delta == best_delta) > 1:
            continue
        best = choices[0]
        out[canonical_uid] = dict(best[3])
        cursor_by_uid[canonical_uid] = int(best[2]) + 1
    return out


def _apply_historical_prediction_universe_gate(
    *,
    contract: _ResolvedRuntimeContract,
    close_ts: datetime,
    candidates: list[Any],
    bar_ordinals: dict[str, int] | None = None,
) -> list[Any]:
    """Historical-only gate: only evaluate rows present in locked repo predictions."""
    if not _is_historical_mode():
        return candidates
    mode = str(_config.historical_prediction_universe_mode).strip().lower()
    if mode in {"off", "disabled", "none"}:
        return candidates
    close_ts_utc = _as_utc_ts(close_ts)

    if mode == "ordinal":
        ordinal_index = _load_historical_prediction_candidate_ordinal_index(contract)
        if not ordinal_index:
            return candidates
        if not bar_ordinals:
            return []
        ordinal_cursor = _historical_prediction_candidate_cursor.setdefault(contract.cache_key, {})
        tolerance = int(_config.historical_prediction_ordinal_tolerance)
        filtered: list[Any] = []
        for cand in candidates:
            canonical_uid = (
                f"oco|{contract.symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
            )
            ordinal_list = ordinal_index.get(canonical_uid, [])
            if not ordinal_list:
                continue
            current_ordinal = bar_ordinals.get(str(cand.bar_ticks))
            if current_ordinal is None:
                continue
            last_idx = int(ordinal_cursor.get(canonical_uid, -1))
            lo = max(0, last_idx + 1)
            lo_search = current_ordinal - tolerance
            idx = bisect_left(ordinal_list, lo_search, lo=lo)
            if idx >= len(ordinal_list):
                continue
            if ordinal_list[idx] > current_ordinal + tolerance:
                continue
            ordinal_cursor[canonical_uid] = idx
            filtered.append(cand)
        return filtered

    if mode in {"tolerant", "nearest"}:
        candidate_index = _load_historical_prediction_candidate_index(contract)
        if not candidate_index:
            return candidates
        candidate_cursor = _historical_prediction_candidate_cursor.setdefault(contract.cache_key, {})
        tolerance = timedelta(seconds=float(_config.historical_prediction_tolerance_sec))
        allow_locked_late_release = str(_config.historical_prediction_payload_mode).strip().lower() in {
            "locked",
            "parquet",
            "override",
        }
        filtered: list[Any] = []
        for cand in candidates:
            canonical_uid = (
                f"oco|{contract.symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
            )
            ts_rows = candidate_index.get(canonical_uid, [])
            if not ts_rows:
                continue
            last_idx = int(candidate_cursor.get(canonical_uid, -1))
            lo = max(0, last_idx + 1)
            idx = bisect_left(ts_rows, close_ts_utc, lo=lo)
            choices: list[tuple[timedelta, datetime, int]] = []
            if idx > lo:
                prev_idx = idx - 1
                prev_ts = ts_rows[prev_idx]
                choices.append((abs(close_ts_utc - prev_ts), prev_ts, prev_idx))
            if idx < len(ts_rows):
                next_idx = idx
                next_ts = ts_rows[next_idx]
                choices.append((abs(next_ts - close_ts_utc), next_ts, next_idx))
            if not choices:
                continue
            choices.sort(key=lambda item: (item[0], item[1], item[2]))
            best_delta = choices[0][0]
            if best_delta > tolerance:
                # In locked-payload replay mode, allow the next unseen locked row
                # to be released shortly after its timestamp, but never hours later.
                if allow_locked_late_release and idx > lo:
                    late_idx = idx - 1
                    late_ts = ts_rows[late_idx]
                    late_delta = close_ts_utc - late_ts
                    if timedelta(0) <= late_delta <= (tolerance * 2):
                        candidate_cursor[canonical_uid] = int(late_idx)
                        filtered.append(cand)
                continue
            best_count = sum(1 for delta, _, _ in choices if delta == best_delta)
            if best_count > 1:
                continue
            candidate_cursor[canonical_uid] = int(choices[0][2])
            filtered.append(cand)
        return filtered

    universe = _load_historical_prediction_universe(contract)
    if not universe:
        return candidates
    allowed = universe.get(close_ts_utc, set())
    if not allowed:
        return []
    filtered: list[Any] = []
    for cand in candidates:
        canonical_uid = (
            f"oco|{contract.symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        )
        if canonical_uid in allowed:
            filtered.append(cand)
    return filtered


def _resolve_account_risk_eval(
    sym: str,
    now_utc: datetime,
    *,
    account_risk_enabled_effective: bool,
) -> dict[str, Any]:
    if (not account_risk_enabled_effective) or (_account_risk_profile is None) or (_state is None):
        return {
            "enabled": False,
            "profile_id": None,
            "allow_trading": True,
            "block_reason": None,
            "snapshot_available": False,
            "trading_day_id": None,
        }

    prof = _account_risk_profile
    latest = _state.get_latest_account_risk_snapshot(sym)
    if latest is None:
        latest = _state.get_latest_account_risk_snapshot(None)

    if latest is None:
        eval_out = evaluate_account_risk_limits(
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

    snaps = _state.get_account_risk_snapshots_since(since_ts=since, symbol=sym)
    if not snaps:
        snaps = _state.get_account_risk_snapshots_since(since_ts=since, symbol=None)

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

    eval_out = evaluate_account_risk_limits(
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
        METRIC_ACCOUNT_RISK_DAILY_HEADROOM.labels(symbol=sym).set(float(daily_headroom))
    if max_headroom is not None:
        METRIC_ACCOUNT_RISK_MAX_HEADROOM.labels(symbol=sym).set(float(max_headroom))
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
    symbol: str
    account_risk_enabled_override: bool | None = Field(
        default=None,
        description="Request-scoped account-risk guard toggle.",
    )
    risk_enabled_override: bool | None = Field(
        default=None,
        description="Broker-neutral request-scoped account-risk guard toggle.",
    )
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
    completed_bar_ticks: list[int] = Field(
        default_factory=list,
        description=(
            "Bar-tick granularities that just completed on the caller side "
            "(e.g. [100], [100,1000]). When provided, prediction is scoped to "
            "matching candidate bar_ticks only."
        ),
    )
    bar_ordinals: dict[str, int] | None = Field(
        default=None,
        description=(
            "Map from bar_ticks (string key) to the 0-indexed count of bars of "
            "that granularity closed since session start. Used by ordinal universe "
            "gate mode to match candidates by position rather than timestamp."
        ),
    )
    run_id: str | None = None

    @model_validator(mode="after")
    def _validate_risk_override(self) -> "PredictRequest":
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


class HealthResponse(BaseModel):
    status: str
    utc_now: datetime
    models_loaded: dict[str, str]
    bar_counts: dict[str, int]
    model_cache_entries: int = 0
    governance_mode: str | None = None
    governance_missing_month_policy: str | None = None
    historical_locks_loaded: int | None = None
    historical_preflight_failed_checks: int | None = None
    historical_preflight_summary: str | None = None


class StatusSymbol(BaseModel):
    symbol: str
    bar_count: int
    model_loaded: bool
    model_month: str | None = None
    has_threshold: bool


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


@app.get("/risk/account/status", response_model=AccountRiskStatusResponse)
async def get_account_status(symbol: str | None = None) -> AccountRiskStatusResponse:
    """Return current broker-neutral account-risk status and account headroom."""
    return await get_account_risk_status(symbol)


@app.get("/risk/account_risk/reservations/status", response_model=AccountRiskReservationsStatusResponse)
async def get_account_risk_reservations_status(symbol: str | None = None) -> AccountRiskReservationsStatusResponse:
    """Return active account-risk reservation totals and rows."""
    sym = str(symbol or "").strip().upper() or None
    if (not _config.account_risk_enabled) or (_account_risk_profile is None) or (_state is None):
        return AccountRiskReservationsStatusResponse(enabled=False, symbol=sym)
    include_pending = bool(_account_risk_profile.allocator.allocator_reserve_pending)
    include_open = bool(_account_risk_profile.allocator.allocator_reserve_open)
    total_reserved = _state.sum_active_account_risk_reserved_loss_ccy(
        symbol=sym,
        include_pending=include_pending,
        include_open=include_open,
    )
    rows = _state.list_active_account_risk_reservations(symbol=sym)
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
) -> AccountRiskReservationsStatusResponse:
    """Return active broker-neutral reservation totals and rows."""
    return await get_account_risk_reservations_status(symbol)


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
    run_id = _effective_run_id(req.run_id)
    account_risk_enabled_effective = req.effective_risk_enabled_override()
    requested_volume_units = _resolve_requested_volume_units(req)
    _append_http_trace(
        endpoint="/predict",
        phase="request",
        run_id=run_id,
        symbol=sym,
        request_payload=req,
    )

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    close_ts = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
    if close_ts.tzinfo is None:
        close_ts = close_ts.replace(tzinfo=timezone.utc)
    else:
        close_ts = close_ts.astimezone(timezone.utc)

    contract = _resolve_runtime_contract(sym, close_ts)
    candidates = contract.candidates
    candidate_count_before_gate = len(candidates)
    if not candidates:
        raise HTTPException(status_code=422, detail=f"No candidates registered for {sym}")
    completed_ticks = _normalize_completed_bar_ticks(req.completed_bar_ticks)
    if completed_ticks:
        candidates = [c for c in candidates if int(getattr(c, "bar_ticks", 0)) in completed_ticks]
        if not candidates:
            return _trace_predict_response(
                req=req,
                sym=sym,
                run_id=run_id,
                results=[],
                reason="completed_bar_ticks_filtered_all_candidates",
                close_ts=close_ts,
                completed_ticks=completed_ticks,
                candidate_count_before_gate=candidate_count_before_gate,
                candidate_count_after_completed_ticks=0,
                candidate_count_after_universe_gate=0,
            )
    candidate_count_after_completed_ticks = len(candidates)
    candidates = _apply_historical_prediction_universe_gate(
        contract=contract,
        close_ts=close_ts,
        candidates=candidates,
        bar_ordinals=req.bar_ordinals,
    )
    if not candidates:
        return _trace_predict_response(
            req=req,
            sym=sym,
            run_id=run_id,
            results=[],
            reason="historical_prediction_universe_gate_filtered_all_candidates",
            close_ts=close_ts,
            completed_ticks=completed_ticks,
            candidate_count_before_gate=candidate_count_before_gate,
            candidate_count_after_completed_ticks=candidate_count_after_completed_ticks,
            candidate_count_after_universe_gate=0,
        )

    _check_warmup(sym, candidates)

    model, thr_cfg = _ensure_model_and_threshold(contract)
    historical_prediction_universe_gated = bool(
        _is_historical_mode() and str(contract.model_binding.get("predictions_path", "")).strip()
    )

    # Compute base rolling features per bar_ticks group
    base_features_by_ticks: dict[int, ModelFeatures] = {}
    regime_quantiles_by_ticks: dict[int, dict[str, float]] = {}

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
            regime_quantiles_by_ticks[bt] = _state.compute_regime_quantiles(sym, bt)

    account_risk_eval = _resolve_account_risk_eval(
        sym,
        close_ts,
        account_risk_enabled_effective=account_risk_enabled_effective,
    )
    _state.expire_stale_account_risk_pending_reservations(
        max_age_seconds=max(60, int(_config.account_risk_pending_reservation_ttl_sec)),
    )

    results, candidate_trace_rows = _build_predictions(
        sym=sym,
        candidates=candidates,
        model=model,
        base_features_by_ticks=base_features_by_ticks,
        regime_quantiles_by_ticks=regime_quantiles_by_ticks,
        close_ts=close_ts,
        thr_cfg=thr_cfg,
        account_risk_eval=account_risk_eval,
        account_risk_enabled_effective=account_risk_enabled_effective,
        account_risk_enabled_override=req.effective_risk_enabled_override(),
        requested_volume_units=requested_volume_units,
        model_month=contract.model_month,
        cap_pips=contract.cap_pips,
        run_id=run_id,
        skip_regime_gate=historical_prediction_universe_gated,
        historical_prediction_overrides=_resolve_historical_prediction_payload_overrides(
            contract=contract,
            close_ts=close_ts,
            candidates=candidates,
        ),
    )

    # Sort by pred_prob descending
    results.sort(key=lambda p: p.pred_prob, reverse=True)
    _trace_predict_response(
        req=req,
        sym=sym,
        run_id=run_id,
        results=results,
        reason="ok",
        close_ts=close_ts,
        completed_ticks=completed_ticks,
        candidate_count_before_gate=candidate_count_before_gate,
        candidate_count_after_completed_ticks=candidate_count_after_completed_ticks,
        candidate_count_after_universe_gate=len(candidates),
        candidate_trace_rows=candidate_trace_rows,
    )
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
    regime_quantiles_by_ticks: dict[int, dict[str, float]],
    close_ts: datetime,
    thr_cfg: dict[str, Any],
    account_risk_eval: dict[str, Any],
    account_risk_enabled_effective: bool,
    account_risk_enabled_override: bool,
    requested_volume_units: float,
    model_month: str,
    cap_pips: float,
    run_id: str | None = None,
    skip_regime_gate: bool = False,
    historical_prediction_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[OcoPrediction], list[dict[str, Any]]]:
    """Build predictions for each candidate using model + account risk portfolio allocator."""
    import numpy as np

    threshold_exec = float(thr_cfg.get("threshold_exec", 0.5))
    threshold_mode = str(thr_cfg.get("threshold_source", "default"))
    logger.debug(
        "Predict %s: threshold_exec=%.4f mode=%s month=%s",
        sym, threshold_exec, threshold_mode, model_month,
    )

    decisions: list[_CandidateDecision] = []
    close_ts_utc = close_ts if close_ts.tzinfo is not None else close_ts.replace(tzinfo=timezone.utc)
    fx_conv = _pip_value_per_unit_usd(
        sym,
        now_utc=close_ts_utc,
        max_age_sec=max(1, int(_config.account_risk_fx_rate_max_age_sec)),
    )
    pip_value_per_unit = fx_conv.get("pip_value_per_unit_usd")
    pip_value_per_unit = float(pip_value_per_unit) if pip_value_per_unit is not None else None
    fx_status = str(fx_conv.get("conversion_status") or "unknown")
    fx_pair = fx_conv.get("conversion_pair")
    fx_rate = fx_conv.get("conversion_rate")
    fx_age = fx_conv.get("conversion_age_sec")

    for cand in candidates:
        base_features = base_features_by_ticks[int(cand.bar_ticks)]
        features = base_features.model_copy(
            update={
                "bar_ticks": float(cand.bar_ticks),
                "horizon": float(cand.horizon),
                "barrier_pips": float(cand.barrier_pips),
            }
        )
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        locked_payload = (
            (historical_prediction_overrides or {}).get(canonical_uid)
            if historical_prediction_overrides is not None
            else None
        )
        regime_name = _candidate_regime_name(cand)
        if skip_regime_gate:
            regime_active = True
        else:
            regime_active = _regime_is_active(
                regime_name,
                features=features,
                close_ts_utc=close_ts_utc,
                regime_q=regime_quantiles_by_ticks.get(int(cand.bar_ticks), {}),
            )
        arr = np.array([features.to_array()], dtype=float)
        if locked_payload is not None:
            pred_prob = float(locked_payload.get("pred_prob") or 0.0)
            curr_threshold = float(locked_payload.get("threshold_exec") or threshold_exec)
            curr_source = "historical_locked_predictions"
            preselected_exec = int(locked_payload.get("selected_exec") or 0)
        else:
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
                # Schedule expired or missing for today. Attempt dynamic rolling threshold
                # from audit_logs — this is the live equivalent of WFO's rolling computation.
                rolling_days = int(thr_cfg.get("rolling_threshold_days", 0))
                exec_q = float(thr_cfg.get("execution_quantile", 0.9))
                min_history = int(thr_cfg.get("rolling_threshold_min_history", 10))
                dynamic_thr = None
                if rolling_days > 0 and _state is not None:
                    dynamic_thr = _state.get_rolling_threshold(
                        symbol=sym,
                        candidate_uid=canonical_uid,
                        exec_q=exec_q,
                        lookback_days=rolling_days,
                        min_history=min_history,
                    )
                
                # Strict Threshold Enforcement Policy:
                # In live mode, we NEVER fall back to static thresholds if a schedule 
                # or rolling history was intended but is unavailable.
                is_live = _config.governance_mode == "live"
                
                if dynamic_thr is not None:
                    curr_threshold = dynamic_thr
                    curr_source = f"{threshold_mode}:rolling_dynamic"
                elif rolling_days > 0:
                    # rolling_days configured but insufficient audit_log history.
                    # ALWAYS block if history is missing and rolling is intended.
                    logger.warning(
                        "No valid threshold for %s %s: schedule expired %s, "
                        "insufficient audit_log history (rolling_days=%d, min_history=%d). "
                        "Blocking candidate.",
                        sym, canonical_uid, day_str, rolling_days, min_history,
                    )
                    curr_threshold = 2.0  # ensures pred_prob (always ≤ 1.0) never qualifies
                    curr_source = f"{threshold_mode}:no_valid_threshold"
                    threshold_blocked = True
                    threshold_block_reason = "ROLLING_HISTORY_GAP"
                elif is_live and schedule:
                    # Schedule existed but expired for today, and no rolling fallback configured.
                    # Block in live mode to avoid static fallback.
                    logger.warning(
                        "No valid threshold for %s %s: schedule expired %s and no rolling fallback. Blocking.",
                        sym, canonical_uid, day_str
                    )
                    curr_threshold = 2.0
                    curr_source = f"{threshold_mode}:schedule_expired"
                    threshold_blocked = True
                    threshold_block_reason = "SCHEDULE_EXPIRED"
                else:
                    # No rolling config and no (expired) schedule — fall back to static threshold_exec.
                    # In research/backtest this is common; in live it uses the scalar threshold_exec.
                    curr_threshold = threshold_exec
                    curr_source = f"{threshold_mode}:static_fallback"

            preselected_exec = 1 if (regime_active and pred_prob >= curr_threshold) else 0
        risk_metrics_snapshot: dict[str, Any] = {
            "account_risk_enabled": bool(account_risk_eval.get("enabled", False)),
            "account_risk_enabled_effective": bool(account_risk_enabled_effective),
            "account_risk_enabled_override": bool(account_risk_enabled_override),
            "account_risk_mode_source": "request_override",
            "account_risk_profile_id": account_risk_eval.get("profile_id"),
            "account_risk_trade_cost_gate_mode": (
                _account_risk_profile.cost_gate.trade_cost_gate_mode if _account_risk_profile is not None else ""
            ),
            "account_risk_allow_trading": bool(account_risk_eval.get("allow_trading", True)),
            "account_risk_account_block_reason": account_risk_eval.get("block_reason"),
            "snapshot_available": bool(account_risk_eval.get("snapshot_available", False)),
            "daily_loss_headroom": account_risk_eval.get("daily_loss_headroom"),
            "max_loss_headroom": account_risk_eval.get("max_loss_headroom"),
            "daily_loss_used": account_risk_eval.get("daily_loss_used"),
            "max_loss_used": account_risk_eval.get("max_loss_used"),
            "trading_day_id": account_risk_eval.get("trading_day_id"),
            "requested_volume_units": float(requested_volume_units),
            "allocator_pip_value_per_unit_usd": pip_value_per_unit,
            "allocator_fx_conversion_status": fx_status,
            "allocator_fx_conversion_pair": fx_pair,
            "allocator_fx_conversion_rate": fx_rate,
            "allocator_fx_conversion_age_sec": fx_age,
            "allocator_fx_rate_max_age_sec": int(max(1, int(_config.account_risk_fx_rate_max_age_sec))),
            "regime_name": regime_name,
            "regime_active": bool(regime_active),
            "historical_locked_payload": bool(locked_payload is not None),
        }
        trade_eval: dict[str, Any] = {"allow_trade": True, "block_reason": None}
        selected_exec = preselected_exec
        risk_blocked = False
        risk_block_reason: str | None = None
        threshold_blocked = False
        threshold_block_reason: str | None = None

        if curr_source in {f"{threshold_mode}:no_valid_threshold", f"{threshold_mode}:schedule_expired"}:
            threshold_blocked = True
            threshold_block_reason = (
                "ROLLING_HISTORY_GAP" if curr_source == f"{threshold_mode}:no_valid_threshold" else "SCHEDULE_EXPIRED"
            )

        if preselected_exec == 1 and account_risk_enabled_effective and (_account_risk_profile is not None):
            trade_eval = evaluate_trade_guard(
                _account_risk_profile,
                account_eval=account_risk_eval,
                pred_prob=pred_prob,
                threshold_exec=curr_threshold,
                barrier_pips=float(cand.barrier_pips),
                cost_est_pips=float(features.cost_est_pips),
            )
            risk_metrics_snapshot.update(trade_eval)
            if _config.account_risk_enforce_blocks and (not bool(trade_eval.get("allow_trade", True))):
                selected_exec = 0
                risk_blocked = True
                risk_block_reason = str(trade_eval.get("block_reason") or "ACCOUNT_RISK_BLOCKED")
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
                threshold_blocked=threshold_blocked,
                threshold_block_reason=threshold_block_reason,
                risk_metrics_snapshot=risk_metrics_snapshot,
                trade_eval=trade_eval,
                risk_rank_score=rank_score,
            )
        )

    allocator_enabled = bool(
        account_risk_enabled_effective
        and _account_risk_profile is not None
        and _account_risk_profile.allocator.allocator_enabled
        and _state is not None
        and _config.account_risk_enforce_blocks
    )

    if allocator_enabled:
        include_pending = bool(_account_risk_profile.allocator.allocator_reserve_pending)
        include_open = bool(_account_risk_profile.allocator.allocator_reserve_open)
        active_reserved_loss_ccy = _state.sum_active_account_risk_reserved_loss_ccy(
            include_pending=include_pending,
            include_open=include_open,
        )
        daily_headroom = account_risk_eval.get("daily_loss_headroom")
        max_headroom = account_risk_eval.get("max_loss_headroom")
        daily_budget = None if daily_headroom is None else float(daily_headroom) * float(_account_risk_profile.allocator.allocator_budget_fraction_daily)
        max_budget = None if max_headroom is None else float(max_headroom) * float(_account_risk_profile.allocator.allocator_budget_fraction_max)
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
            - float(_account_risk_profile.allocator.allocator_min_headroom_buffer_ccy)
            - float(active_reserved_loss_ccy)
        )
        allocator_remaining = max(0.0, allocator_remaining)
        METRIC_ACCOUNT_RISK_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(active_reserved_loss_ccy))

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
                d.risk_block_reason = "ACCOUNT_RISK_PIP_VALUE_UNAVAILABLE"
                d.risk_metrics_snapshot["allocator_remaining_before_ccy"] = float(allocator_remaining)
                METRIC_RISK_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                METRIC_ACCOUNT_RISK_ALLOCATOR_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                continue

            gross_loss_pips = max(
                0.0,
                float(d.cand.barrier_pips) + float(cap_pips) + float(est_cost),
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
                METRIC_ACCOUNT_RISK_ALLOCATOR_ADMITTED_TOTAL.labels(symbol=sym).inc()
            else:
                d.selected_exec = 0
                d.risk_blocked = True
                d.risk_block_reason = "ACCOUNT_RISK_RESERVED_BUDGET_EXCEEDED"
                d.risk_metrics_snapshot["allocator_admitted"] = False
                d.risk_headroom_after_ccy = float(allocator_remaining)
                METRIC_RISK_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()
                METRIC_ACCOUNT_RISK_ALLOCATOR_BLOCKS_TOTAL.labels(symbol=sym, reason=d.risk_block_reason).inc()

        METRIC_ACCOUNT_RISK_RESERVED_LOSS_CCY.labels(symbol=sym).set(float(active_reserved_loss_ccy + newly_reserved_ccy))

    results: list[OcoPrediction] = []
    trace_rows: list[dict[str, Any]] = []
    for d in decisions:
        if _state is not None:
            _state.log_predict_evaluation(
                symbol=sym,
                candidate_uid=d.candidate_uid,
                pred_prob=d.pred_prob,
                threshold=d.curr_threshold,
                preselected_exec=d.preselected_exec,
                selected_exec=d.selected_exec,
                threshold_blocked=bool(getattr(d, "threshold_blocked", False)),
                threshold_block_reason=getattr(d, "threshold_block_reason", None),
                risk_blocked=d.risk_blocked,
                risk_block_reason=d.risk_block_reason,
                model_month=model_month,
                close_ts=close_ts,
                run_id=run_id,
            )

        if d.selected_exec == 1 and _state is not None:
            if allocator_enabled and d.risk_reserved and (d.risk_reserved_amount_ccy is not None):
                reservation_id = _state.create_account_risk_reservation(
                    symbol=sym,
                    candidate_uid=d.candidate_uid,
                    reserved_loss_ccy=float(d.risk_reserved_amount_ccy),
                    barrier_pips=float(d.cand.barrier_pips),
                    cap_pips=float(cap_pips),
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
                close_ts=close_ts,
                run_id=run_id,
            )

        if (
            _state is not None
            and account_risk_enabled_effective
            and (_account_risk_profile is not None)
            and d.preselected_exec == 1
        ):
            event_status = "ADMITTED" if d.selected_exec == 1 else "BLOCKED"
            _state.log_account_risk_allocator_event(
                symbol=sym,
                candidate_uid=d.candidate_uid,
                status=event_status,
                block_reason=d.risk_block_reason,
                reserved_loss_ccy=d.risk_reserved_amount_ccy,
                requested_volume_units=float(requested_volume_units),
                pred_prob=float(d.pred_prob),
                threshold_exec=float(d.curr_threshold),
                risk_rank_score=d.risk_rank_score,
                reservation_id=d.risk_reservation_id,
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
                cap_pips=float(cap_pips),
                threshold_source=d.curr_source,
                model_month=model_month,
                threshold_blocked=d.threshold_blocked,
                threshold_block_reason=d.threshold_block_reason,
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
        trace_rows.append(
            {
                "candidate_uid": d.candidate_uid,
                "close_ts": close_ts,
                "pred_prob": float(d.pred_prob),
                "threshold_exec": float(d.curr_threshold),
                "selected_exec": int(d.selected_exec),
                "preselected_exec": int(d.preselected_exec),
                "risk_blocked": bool(d.risk_blocked),
                "risk_block_reason": d.risk_block_reason,
                "features": d.features.model_dump(),
            }
        )
    return results, trace_rows


@app.post("/predict/warmup", status_code=201)
async def predict_warmup(req: WarmupRequest) -> dict:
    """Score buffered bars through the model to seed audit_logs for rolling threshold.

    Iterates all bars in the tick_bars buffer for the given symbol, computes
    features at the CURRENT buffer state (not a historical replay), and writes
    one audit_log entry per eligible bar using the bar's historical close_ts.
    This seeds the rolling threshold history needed when the threshold schedule
    has expired.

    Called once per symbol after backfill completes on startup.
    Idempotent: safe to call multiple times (appends to audit_logs).
    """
    import numpy as np

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    sym = req.symbol.upper()
    run_id = req.run_id or "warmup"

    close_ts_now = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
    contract = _resolve_runtime_contract(sym, close_ts_now)
    if not contract.candidates:
        raise HTTPException(status_code=422, detail=f"No candidates for {sym}")

    model, thr_cfg = _ensure_model_and_threshold(contract)
    if model is None:
        raise HTTPException(status_code=422, detail=f"No model loaded for {sym}")

    # Fetch all close_ts values from the bar buffer for this symbol
    bar_ticks = int(contract.candidates[0].bar_ticks)
    rows = _state._con.execute(
        "SELECT close_ts FROM tick_bars WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id",
        [sym, bar_ticks],
    ).fetchall()

    warmup_needed = _state._cfg.full_warmup_bars
    if len(rows) < warmup_needed:
        return {
            "ok": True,
            "symbol": sym,
            "audit_events_written": 0,
            "skipped_reason": f"insufficient_bars:{len(rows)}<{warmup_needed}",
        }

    # Compute features once from current buffer state
    n_written = 0
    for cand in contract.candidates:
        feats = _state.compute_features(sym, bar_ticks, cand.horizon, cand.barrier_pips)
        if feats is None:
            continue
        arr = np.array([feats.to_array()], dtype=float)
        with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
            pred_prob = float(model.predict_proba(arr)[:, 1][0])
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        static_thr = float(thr_cfg.get("threshold_exec", 0.5))
        for (close_ts_val,) in rows:
            close_ts_bar = close_ts_val
            if hasattr(close_ts_bar, "tzinfo") and close_ts_bar.tzinfo is None:
                close_ts_bar = close_ts_bar.replace(tzinfo=timezone.utc)
            _state.log_audit_event(
                symbol=sym,
                candidate_uid=canonical_uid,
                pred_prob=pred_prob,
                threshold=static_thr,
                features=feats,
                model_month=contract.model_month,
                close_ts=close_ts_bar,
                run_id=run_id,
            )
            n_written += 1

    logger.info("predict_warmup: wrote %d audit events for %s", n_written, sym)
    return {"ok": True, "symbol": sym, "audit_events_written": n_written}


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
    )
    if _config.account_risk_enabled and (_account_risk_profile is not None):
        _state.promote_account_risk_reservation(
            broker_pos_id=req.broker_pos_id,
            reservation_id=req.reservation_id,
            candidate_uid=req.candidate_uid,
            symbol=req.symbol,
        )
    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, status="OPEN").inc()
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


@app.get("/state/checkpoint")
async def checkpoint_state():
    """Force DuckDB to flush WAL to the on-disk database file."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    _state._con.execute("CHECKPOINT")
    return {"status": "ok", "checkpointed_at": datetime.now(tz=timezone.utc).isoformat()}


@app.post("/state/seed_audit_history", status_code=201)
async def seed_audit_history(req: SeedAuditHistoryRequest) -> dict:
    """Replay Dukascopy parquets through the model to seed audit_logs.

    Creates a rolling pred_prob distribution so get_rolling_threshold()
    returns a calibrated value on the first live predict call after startup.
    Uses an isolated in-memory StateManager for replay; writes to the live
    DB via _state.log_audit_event() (single-writer pattern).
    Idempotent: NOT idempotent — repeated calls with the same run_id append duplicate rows to audit_logs; the rolling quantile is robust to duplicates but the run_jforex_live.py caller should call this only once per startup.
    """
    import numpy as np
    import pandas as pd

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    ticks_dir = Path(_config.dukascopy_ticks_dir)
    if not ticks_dir.exists():
        raise HTTPException(
            status_code=422,
            detail=f"dukascopy_ticks_dir not found: {ticks_dir}",
        )

    symbols = [s.upper() for s in (req.symbols or _config.symbols)]
    now_ts = datetime.now(tz=timezone.utc)
    start_dt = now_ts - timedelta(days=req.days_back)
    events_by_symbol: dict[str, int] = {}

    for sym in symbols:
        sym_dir = ticks_dir / sym
        if not sym_dir.exists():
            logger.warning("seed_audit_history: no parquet dir for %s at %s", sym, sym_dir)
            events_by_symbol[sym] = 0
            continue

        # Find monthly parquet files that overlap [start_dt, now_ts]
        start_ym = start_dt.strftime("%Y%m")
        end_ym = now_ts.strftime("%Y%m")
        relevant = sorted(
            f for f in sym_dir.glob(f"{sym}_*_ticks.parquet")
            if (ym := f.stem.removeprefix(f"{sym}_").removesuffix("_ticks"))
            and start_ym <= ym <= end_ym
        )

        if not relevant:
            logger.warning(
                "seed_audit_history: no parquets for %s in %s–%s", sym, start_ym, end_ym
            )
            events_by_symbol[sym] = 0
            continue

        try:
            frames = [pd.read_parquet(f, columns=["timestamp", "bid", "ask"]) for f in relevant]
            df = pd.concat(frames, ignore_index=True)
            # Normalise to UTC-aware
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
            df = (
                df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= now_ts)]
                .sort_values("timestamp")
                .reset_index(drop=True)
            )
        except Exception as exc:
            logger.warning("seed_audit_history: failed to read parquets for %s: %s", sym, exc)
            events_by_symbol[sym] = 0
            continue

        if df.empty:
            events_by_symbol[sym] = 0
            continue

        # Resolve live model contract — uses identical canonical_uid format as /predict
        try:
            contract = _resolve_runtime_contract(sym, now_ts)
        except HTTPException as exc:
            logger.warning(
                "seed_audit_history: cannot resolve contract for %s: %s", sym, exc.detail
            )
            events_by_symbol[sym] = 0
            continue
        if not contract.candidates:
            events_by_symbol[sym] = 0
            continue
        try:
            model, thr_cfg = _ensure_model_and_threshold(contract)
        except HTTPException as exc:
            logger.warning(
                "seed_audit_history: cannot load model for %s: %s", sym, exc.detail
            )
            events_by_symbol[sym] = 0
            continue
        if model is None:
            events_by_symbol[sym] = 0
            continue

        static_thr = float(thr_cfg.get("threshold_exec", 0.5))
        bar_ticks = int(contract.candidates[0].bar_ticks)
        if len({c.bar_ticks for c in contract.candidates}) != 1:
            logger.warning(
                "seed_audit_history: mixed bar_ticks for %s — skipping (only uniform bar_ticks supported)",
                sym,
            )
            events_by_symbol[sym] = 0
            continue

        # Isolated replay — never writes to live tick_bars
        replay_state = StateManager(
            vol_window=_config.vol_window,
            cost_window=_config.cost_window,
        )
        replay_agg = TickAggregator(bar_ticks=bar_ticks)
        n_written = 0

        try:
            # Batch-convert to IncomingTick and aggregate in one pass
            ticks = [
                IncomingTick(
                    symbol=sym,
                    timestamp=row.timestamp.to_pydatetime(),
                    bid=float(row.bid),
                    ask=float(row.ask),
                )
                for row in df.itertuples(index=False)
            ]
            bars = replay_agg.add_ticks(ticks)
            if not bars:
                events_by_symbol[sym] = 0
                continue

            # Convert bars to DataFrame for vectorized processing
            bars_df = pd.DataFrame([b.model_dump() for b in bars])

            for cand in contract.candidates:
                # ── Vectorized Feature Computation ──
                # Process the entire history of bars in one pass of rolling windows
                features_df = compute_feature_matrix_from_bars(
                    bars_df,
                    symbol=sym,
                    bar_ticks=bar_ticks,
                    horizon=cand.horizon,
                    barrier_pips=cand.barrier_pips,
                    cfg=FeatureConfig(
                        vol_window=_config.vol_window,
                        cost_window=_config.cost_window,
                    ),
                )
                if features_df is None or features_df.empty:
                    continue

                # Identify rows with sufficient history (no NaNs in features)
                valid_mask = features_df.notna().all(axis=1)
                valid_features = features_df[valid_mask]
                if valid_features.empty:
                    continue

                # ── Batch Inference ──
                # Match ModelFeatures schema order for CatBoost input
                X = valid_features[[
                    "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
                    "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z", "tick_rate_z",
                    "hour_utc", "hl_first", "hl_first_mean_24", "hl_pos_frac_mean_24",
                    "bar_ticks", "horizon", "barrier_pips"
                ]].values
                
                # Metadata-level inference: release GIL during bulk CatBoost scoring if possible
                with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
                    pred_probs = model.predict_proba(X)[:, 1]

                # ── Batch Logging to DuckDB ──
                canonical_uid = (
                    f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
                )
                valid_bars = bars_df.loc[valid_features.index]
                events_batch = []
                
                for i in range(len(valid_features)):
                    row_feat = valid_features.iloc[i]
                    # Serialize the features into the JSON format expected by audit_logs
                    feat_obj = ModelFeatures(**row_feat.to_dict())
                    
                    events_batch.append((
                        valid_bars.iloc[i]["close_ts"],
                        sym,
                        canonical_uid,
                        float(pred_probs[i]),
                        static_thr,
                        feat_obj.model_dump_json(),
                        contract.model_month,
                        req.run_id,
                    ))

                _state.log_audit_event_batch(events_batch)
                n_written += len(events_batch)
        finally:
            replay_state.close()

        events_by_symbol[sym] = n_written
        logger.info("seed_audit_history: wrote %d events for %s", n_written, sym)

    total = sum(events_by_symbol.values())
    return {"ok": True, "events_by_symbol": events_by_symbol, "total_events": total}


@app.post("/trades/touch")
async def touch_trade(req: TradeTouchRequest):
    """Record that a position's barrier was touched."""
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
    res = _state._con.execute("SELECT MAX(row_id) FROM tick_bars WHERE symbol = ?", [sym]).fetchone()
    touch_bar_id = res[0] if res and res[0] is not None else 0
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

    METRIC_TRADES_TOTAL.labels(symbol=req.symbol, status=req.status.value).inc()
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
    """System health: model validity, buffer depths."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    bar_counts: dict[str, int] = {}
    for sym in _config.symbols:
        bar_counts[sym] = _state.bar_count(sym, 100)

    mode = str(_config.governance_mode).strip().lower()
    has_runtime_contracts = bool(_models)
    if _is_historical_mode():
        has_runtime_contracts = has_runtime_contracts or (_historical_entries_loaded > 0)

    return HealthResponse(
        status="ok" if has_runtime_contracts else "no_models",
        utc_now=datetime.now(tz=timezone.utc),
        models_loaded=dict(_model_months),
        bar_counts=bar_counts,
        model_cache_entries=len(_models),
        governance_mode=mode,
        governance_missing_month_policy=(
            str(_config.governance_missing_month_policy).strip().lower()
            if _is_historical_mode()
            else None
        ),
        historical_locks_loaded=_historical_entries_loaded if _is_historical_mode() else None,
        historical_preflight_failed_checks=(
            _historical_preflight_failed_checks if _is_historical_mode() else None
        ),
        historical_preflight_summary=(
            _historical_preflight_summary if _is_historical_mode() else None
        ),
    )


@app.get("/status")
async def status() -> list[StatusSymbol]:
    """Per-symbol detailed status."""
    out: list[StatusSymbol] = []
    for sym in _config.symbols:
        has_threshold = bool(_thresholds.get(sym))
        if (not has_threshold) and _is_historical_mode():
            pref = f"{sym}|"
            has_threshold = any(k.startswith(pref) for k in _thresholds)
        out.append(StatusSymbol(
            symbol=sym,
            bar_count=_state.bar_count(sym, 100) if _state else 0,
            model_loaded=_has_loaded_model_for_symbol(sym),
            model_month=_latest_loaded_month_for_symbol(sym),
            has_threshold=has_threshold,
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


@app.post("/reload")
async def reload_models() -> dict:
    """Hot-reload models from disk without restarting the server."""
    global _registry, _historical_registry, _historical_entries_loaded
    global _historical_preflight_failed_checks, _historical_preflight_summary
    global _historical_prediction_universes, _historical_prediction_candidate_index
    global _historical_prediction_candidate_ordinal_index
    global _historical_prediction_candidate_cursor, _historical_prediction_payload_rows
    global _historical_prediction_payload_cursor

    if _is_historical_mode():
        hist_dir = Path(str(_config.governance_history_dir))
        _historical_registry = HistoricalCandidateRegistry.load(hist_dir)
        _run_historical_preflight(hist_dir)
        _registry = None
        _historical_entries_loaded = len(_historical_registry._entries)
    else:
        _registry = CandidateRegistry.load(
            os.getenv("BEHEMOTH_GOVERNANCE_DIR", "configs/research/governance/oco")
        )
        _historical_registry = None
        _historical_entries_loaded = 0
        _historical_preflight_failed_checks = 0
        _historical_preflight_summary = ""

    _load_models()
    _historical_prediction_universes = {}
    _historical_prediction_candidate_index = {}
    _historical_prediction_candidate_ordinal_index = {}
    _historical_prediction_candidate_cursor = {}
    _historical_prediction_payload_rows = {}
    _historical_prediction_payload_cursor = {}
    return {
        "ok": True,
        "models_loaded": dict(_model_months),
        "model_cache_entries": len(_models),
        "governance_mode": str(_config.governance_mode).strip().lower(),
        "historical_locks_loaded": _historical_entries_loaded if _is_historical_mode() else None,
        "historical_preflight_failed_checks": (
            _historical_preflight_failed_checks if _is_historical_mode() else None
        ),
    }


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

    if _config.record_raw_ticks and _is_historical_mode():
        _state.record_raw_tick(tick, source="historical_backtest")

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
