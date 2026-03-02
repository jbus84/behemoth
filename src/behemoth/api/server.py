"""FastAPI inference server for the OCO stop-limit strategy.

Endpoints:
    POST /bars         – Ingest a new tick bar from cTrader
    POST /predict      – Compute features and run CatBoost inference
    GET  /health       – Model validity, buffer depth, and system status
    GET  /status       – Per-symbol state summary (bar counts, last timestamps)

Model loading:
    On startup (or hot-reload via POST /reload), the server loads the
    latest CatBoost ``.cbm`` binary and its paired threshold JSON from
    ``models/oco/<SYMBOL>_model_<MONTH>.cbm``.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.behemoth.core.schemas import IncomingTick, IncomingTickBar, ModelFeatures, OcoPrediction
from src.behemoth.runtime.state import StateManager
from src.behemoth.runtime.tick_aggregator import TickAggregator
from src.behemoth.core.registry import CandidateRegistry
from src.behemoth.core.features import FeatureConfig, compute_features_from_bars

logger = logging.getLogger("behemoth.api")

# ── App ───────────────────────────────────────────────────────────────

# ── Global State ──────────────────────────────────────────────────────

_state: StateManager | None = None
_aggregator: TickAggregator | None = None
_registry: CandidateRegistry | None = None
_models: dict[str, object] = {}          # symbol -> loaded CatBoostClassifier
_thresholds: dict[str, dict] = {}        # symbol -> threshold config
_model_months: dict[str, str] = {}       # symbol -> "YYYY-MM"
_models_dir: Path = Path("models/oco")


class AppConfig(BaseModel):
    """Runtime configuration for the inference server."""
    vol_window: int = 96
    cost_window: int = 288
    models_dir: str = Field(default_factory=lambda: os.getenv("BEHEMOTH_MODELS_DIR", "models/oco"))
    registry_path: str = "configs/research/governance/oco_rule_universe_registry.yaml"
    symbols: list[str] = Field(
        default=["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    )


_config = AppConfig()


# ── Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event."""
    global _state, _aggregator, _registry, _models_dir
    _state = StateManager(
        vol_window=_config.vol_window,
        cost_window=_config.cost_window,
    )
    _aggregator = TickAggregator(bar_ticks=100)
    try:
        _registry = CandidateRegistry.load("configs/research/governance/oco")
        logger.info("Loaded %d candidates from governance locks", len(_registry.all_candidates()))
    except FileNotFoundError:
        _registry = None
        logger.warning("Governance lock dir not found — using empty registry")
    _models_dir = Path(_config.models_dir)
    _load_models()
    logger.info("Behemoth API started. Models dir: %s", _models_dir)
    yield
    if _state:
        _state.close()
        _state = None


app = FastAPI(
    title="Behemoth OCO Inference API",
    version="0.1.0",
    description="Production inference server for the tick-based OCO stop-limit strategy.",
    lifespan=lifespan,
)

# Mount dashboard sub-router
from src.behemoth.api.dashboard import router as dashboard_router
app.include_router(dashboard_router)


def _load_models() -> None:
    """Scan models directory and load latest .cbm per symbol."""
    global _models, _thresholds, _model_months
    if not _models_dir.exists():
        logger.warning("Models directory %s does not exist yet.", _models_dir)
        return

    try:
        from catboost import CatBoostClassifier
    except ImportError:
        logger.error("CatBoost not installed — predictions will be unavailable.")
        return

    for sym in _config.symbols:
        # Find latest model file by sorting
        candidates = sorted(_models_dir.glob(f"{sym}_model_*.cbm"))
        
        force_month = os.getenv("BEHEMOTH_FORCE_MODEL_MONTH")
        if force_month:
            candidates = [c for c in candidates if force_month in c.stem]
            
        if not candidates:
            logger.warning("No model found for %s (force_month=%s)", sym, force_month)
            continue
        latest = candidates[-1]  # lexicographic sort = chronological for YYYY-MM
        month = latest.stem.split("_")[-1]  # e.g. "2025-12"

        model = CatBoostClassifier()
        model.load_model(str(latest))
        _models[sym] = model
        _model_months[sym] = month
        logger.info("Loaded model for %s: %s (month=%s)", sym, latest.name, month)

        # Load paired threshold JSON
        thr_path = latest.with_suffix(".json")
        if thr_path.exists():
            _thresholds[sym] = json.loads(thr_path.read_text())
            logger.info("Loaded threshold config for %s", sym)
        else:
            _thresholds[sym] = {}
            logger.warning("No threshold JSON for %s at %s", sym, thr_path)


# ── Request / Response Models ─────────────────────────────────────────

class PredictRequest(BaseModel):
    """Prediction request. Just specify the symbol — candidates come from registry."""
    symbol: str


class HealthResponse(BaseModel):
    status: str
    utc_now: datetime
    models_loaded: dict[str, str]
    bar_counts: dict[str, int]


class StatusSymbol(BaseModel):
    symbol: str
    bar_count: int
    model_loaded: bool
    model_month: Optional[str] = None
    has_threshold: bool


class BackfillRequest(BaseModel):
    """Batch of raw ticks for instant warmup."""
    symbol: str
    bar_ticks: int = 100
    ticks: list[IncomingTick]


# ── Endpoints ─────────────────────────────────────────────────────────

@app.post("/bars", status_code=201)
async def ingest_bar(bar: IncomingTickBar) -> dict:
    """Ingest a new tick bar into the state buffer."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    _state.append_bar(bar)
    return {
        "ok": True,
        "symbol": bar.symbol,
        "bar_count": _state.bar_count(bar.symbol),
    }


@app.post("/predict", response_model=list[OcoPrediction])
async def predict(req: PredictRequest) -> list[OcoPrediction]:
    """Evaluate all registry candidates for a symbol and return predictions.

    Computes rolling features once, then runs CatBoost inference for each
    candidate (different horizon/barrier_pips). Returns results sorted by
    pred_prob descending.
    """
    sym = req.symbol.upper()

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    # Get candidates from registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Candidate registry not loaded")

    candidates = _registry.get_candidates(sym)
    if not candidates:
        raise HTTPException(status_code=422, detail=f"No candidates registered for {sym}")

    # Check warmup
    bar_count = _state.bar_count(sym)
    warmup_needed = max(_config.vol_window, _config.cost_window) + 1
    if bar_count < warmup_needed:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient warmup bars for {sym}. "
                   f"Have {bar_count}, need ≥{warmup_needed}.",
        )

    # Load model
    model = _models.get(sym)
    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"No CatBoost model loaded for {sym}. "
                   f"Export models via run_tick_opportunity_monthly_wfo.py first.",
        )

    # Compute base rolling features once (horizon/barrier set later per candidate)
    base_features = _state.compute_features(
        symbol=sym,
        bar_ticks=candidates[0].bar_ticks,
        horizon=candidates[0].horizon,
        barrier_pips=candidates[0].barrier_pips,
    )
    if base_features is None:
        raise HTTPException(status_code=422, detail=f"Feature computation failed for {sym}")

    import numpy as np

    thr_cfg = _thresholds.get(sym, {})
    threshold_exec = float(thr_cfg.get("threshold_exec", 0.5))
    threshold_source = str(thr_cfg.get("threshold_source", "default"))
    model_month = _model_months.get(sym, "unknown")
    
    # In live trading this is functionally current time, but in replay we must
    # exactly align with the state DB's reconstructed chronological limit.
    close_ts = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)

    results: list[OcoPrediction] = []
    for cand in candidates:
        # Override structural features per candidate
        features = base_features.model_copy(update={
            "bar_ticks": float(cand.bar_ticks),
            "horizon": float(cand.horizon),
            "barrier_pips": float(cand.barrier_pips),
        })
        arr = np.array([features.to_array()], dtype=float)
        pred_prob = float(model.predict_proba(arr)[:, 1][0])

        # Offline format expects: library|symbol|bar_ticks|h_horizon|candidate_basename
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"

        results.append(OcoPrediction(
            symbol=sym,
            close_ts=close_ts,
            candidate_uid=canonical_uid,
            pred_prob=pred_prob,
            threshold_exec=threshold_exec,
            selected_exec=1 if pred_prob >= threshold_exec else 0,
            horizon=int(cand.horizon),
            barrier_pips=float(cand.barrier_pips),
            threshold_source=threshold_source,
            model_month=model_month,
        ))

    # Sort by pred_prob descending
    results.sort(key=lambda p: p.pred_prob, reverse=True)
    return results


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """System health: model validity, buffer depths."""
    bar_counts: dict[str, int] = {}
    if _state:
        for sym in _config.symbols:
            bar_counts[sym] = _state.bar_count(sym)

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
            bar_count=_state.bar_count(sym) if _state else 0,
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
    if _state is None or _aggregator is None:
        raise HTTPException(status_code=503, detail="Not initialized")

    bars = _aggregator.add_ticks(req.ticks)
    for bar in bars:
        _state.append_bar(bar)

    sym = req.symbol.upper()
    count = _state.bar_count(sym)
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
    if _state is None or _aggregator is None:
        raise HTTPException(status_code=503, detail="Not initialized")

    bars = _aggregator.add_ticks([tick])
    bar_completed = False
    for bar in bars:
        _state.append_bar(bar)
        bar_completed = True

    sym = tick.symbol.upper()
    return {
        "ok": True,
        "symbol": sym,
        "bar_completed": bar_completed,
        "bar_count": _state.bar_count(sym),
    }
