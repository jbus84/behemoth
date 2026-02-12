import hashlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import cast

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from .cache import cache_get_position, cache_invalidate_position, cache_set_position
from .db import Base, engine, get_db
from .guardrail import get_guardrail_state, is_trade_allowed, update_guardrail_on_close
from .logging import configure_logging, log_event
from .metrics import (
    GUARDRAIL_BLOCKS,
    RISK_HALTS,
    metrics_response,
    refresh_state_metrics,
    timeit,
    track_request,
)
from .models import (
    GuardrailState,
    IdempotencyKey,
    Order,
    OrderStatus,
    Position,
    PositionEvent,
    PositionStatus,
)
from .predict import generate_mom_events_for_pair
from .risk import (
    check_risk_on_create,
    get_or_create_account_state,
    reset_account_halt,
    update_account_on_close,
)
from .runtime import validate_runtime_config
from .schemas import (
    AccountStateResponse,
    GuardrailStateResponse,
    GuardrailPausedResponse,
    OrderCreate,
    OrderResponse,
    PositionClose,
    PositionCreate,
    PositionOpen,
    PositionResponse,
    RiskHaltRequest,
)
from .settings import settings
from .state import can_transition
from .validation import (
    compare_pipeline_to_db,
    compare_predictions_to_pipeline,
    summary_for_bar,
    summary_from_db,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    validate_runtime_config()
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Behemoth Position API", version="0.1.0", lifespan=lifespan)
logger = logging.getLogger("behemoth.api")


def _hash_request(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _payload_json(payload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return payload


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    done = timeit()
    response = await call_next(request)
    duration = done()
    if settings.metrics_enabled:
        route = request.scope.get("route")
        path = route.path if route else request.url.path
        track_request(request.method, path, response.status_code, duration)
    return response


@app.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    refresh_state_metrics(db)
    return metrics_response()


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"ok": True}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    return healthz(db)


@app.get("/validation/pipeline/{bar}")
def validation_pipeline(bar: str, guardrail: bool = False):
    try:
        return summary_for_bar(bar, guardrail=guardrail)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/predictions/{bar}/{pair:path}")
def predictions(
    bar: str,
    pair: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
    offset: int = 0,
    limit: int = 1000,
):
    events = generate_mom_events_for_pair(bar, pair)
    if start_ts is not None:
        events = [e for e in events if e["entry_ts"] >= start_ts]
    if end_ts is not None:
        events = [e for e in events if e["entry_ts"] <= end_ts]
    total = len(events)
    page = events[offset : offset + limit]
    return {
        "pair": pair,
        "bar": bar,
        "total": total,
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "events": page,
    }


@app.get("/validation/db/{bar}")
def validation_db(bar: str, guardrail: bool = False, db: Session = Depends(get_db)):
    return summary_from_db(db, bar, guardrail=guardrail)


@app.get("/validation/compare/{bar}")
def validation_compare(
    bar: str,
    tol_mean: float = 1e-6,
    tol_total: float = 1e-6,
    tol_max_dd: float = 1e-6,
    tol_sharpe: float = 1e-6,
    tol_sharpe_active: float = 1e-6,
    tol_sharpe_trade: float = 1e-6,
    tol_win_rate: float = 1e-6,
    match_ts: bool = False,
    ts_tolerance_ns: int = 0,
    match_pair: bool = False,
    guardrail: bool = False,
    db: Session = Depends(get_db),
):
    return compare_pipeline_to_db(
        db,
        bar,
        tol_mean=tol_mean,
        tol_total=tol_total,
        tol_max_dd=tol_max_dd,
        tol_sharpe=tol_sharpe,
        tol_sharpe_active=tol_sharpe_active,
        tol_sharpe_trade=tol_sharpe_trade,
        tol_win_rate=tol_win_rate,
        match_ts=match_ts,
        ts_tolerance_ns=ts_tolerance_ns,
        match_pair=match_pair,
        guardrail=guardrail,
    )


@app.get("/validation/predictions/{bar}/{pair:path}")
def validation_predictions(
    bar: str,
    pair: str,
    ts_tolerance_ns: int = 0,
):
    return compare_predictions_to_pipeline(bar, pair, ts_tolerance_ns)


@app.post("/positions", response_model=PositionResponse)
def create_position(
    payload: PositionCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    req_hash = _hash_request(payload.model_dump())

    if idempotency_key:
        existing = db.query(IdempotencyKey).filter_by(key=idempotency_key).first()
        if existing:
            if existing.request_hash != req_hash:
                raise HTTPException(
                    status_code=409, detail="Idempotency key reuse with different payload"
                )
            pos = db.query(Position).filter_by(id=existing.position_id).first()
            if pos is None:
                raise HTTPException(
                    status_code=404, detail="Position not found for idempotency key"
                )
            return pos

    if payload.size <= 0:
        raise HTTPException(status_code=400, detail="size must be > 0")

    if settings.risk_enabled:
        risk_ok, risk_detail = check_risk_on_create(
            db, payload.strategy_id, payload.pair, payload.size
        )
        if not risk_ok:
            reason = risk_detail.get("error", "risk_halted")
            RISK_HALTS.labels(strategy_id=payload.strategy_id, reason=str(reason)).inc()
            raise HTTPException(status_code=409, detail=risk_detail)

    if settings.guardrail_enabled:
        entry_ts = payload.entry_ts or _now()
        allowed, pause_until, _ = is_trade_allowed(db, payload.strategy_id, payload.pair, entry_ts)
        if not allowed:
            GUARDRAIL_BLOCKS.labels(strategy_id=payload.strategy_id, pair=payload.pair).inc()
            detail = {
                "error": "guardrail_paused",
                "pause_until": pause_until.isoformat() if pause_until else None,
            }
            raise HTTPException(status_code=409, detail=detail)

    account_state = get_or_create_account_state(db, payload.strategy_id)
    account_equity = float(cast(float, account_state.equity))
    alloc_frac = float(payload.size) / account_equity

    pos = Position(
        strategy_id=payload.strategy_id,
        pair=payload.pair,
        side=payload.side,
        active_leg=payload.active_leg,
        size=payload.size,
        notional_usd=payload.size,
        alloc_frac=alloc_frac,
        entry_equity=account_equity,
        entry_price=payload.entry_price,
        entry_ts=payload.entry_ts,
        meta=payload.metadata,
        status=PositionStatus.PENDING,
    )
    db.add(pos)
    db.flush()

    if idempotency_key:
        db.add(
            IdempotencyKey(
                key=idempotency_key, request_hash=req_hash, position_id=cast(str, pos.id)
            )
        )

    pos_id = cast(str, pos.id)
    db.add(PositionEvent(position_id=pos_id, event_type="CREATED", payload=_payload_json(payload)))
    db.commit()
    db.refresh(pos)

    cache_set_position(pos_id, PositionResponse.model_validate(pos).model_dump())
    log_event(
        logger,
        "position_created",
        position_id=pos_id,
        strategy_id=payload.strategy_id,
        pair=payload.pair,
    )
    return pos


@app.get("/positions/{position_id}", response_model=PositionResponse)
def get_position(position_id: str, db: Session = Depends(get_db)):
    cached = cache_get_position(position_id)
    if cached:
        return cached
    pos = db.query(Position).filter_by(id=position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    cache_set_position(cast(str, pos.id), PositionResponse.model_validate(pos).model_dump())
    return pos


@app.get("/positions", response_model=list[PositionResponse])
def list_positions(
    status: PositionStatus | None = None,
    pair: str | None = None,
    strategy_id: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Position)
    if status:
        q = q.filter_by(status=status)
    if pair:
        q = q.filter_by(pair=pair)
    if strategy_id:
        q = q.filter_by(strategy_id=strategy_id)
    return q.order_by(Position.created_at.desc()).all()


@app.post("/positions/{position_id}/open", response_model=PositionResponse)
def open_position(position_id: str, payload: PositionOpen, db: Session = Depends(get_db)):
    pos = db.query(Position).filter_by(id=position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    pos_status = cast(PositionStatus, pos.status)
    if not can_transition(pos_status, PositionStatus.OPEN):
        raise HTTPException(status_code=409, detail=f"Invalid transition from {pos_status}")

    pos.status = PositionStatus.OPEN
    pos.entry_price = payload.entry_price
    pos.entry_ts = payload.entry_ts or _now()
    pos.version += 1

    db.add(
        PositionEvent(
            position_id=cast(str, pos.id), event_type="OPENED", payload=_payload_json(payload)
        )
    )
    db.commit()
    db.refresh(pos)
    cache_invalidate_position(cast(str, pos.id))
    log_event(logger, "position_opened", position_id=cast(str, pos.id))
    return pos


@app.post("/positions/{position_id}/close", response_model=PositionResponse)
def close_position(position_id: str, payload: PositionClose, db: Session = Depends(get_db)):
    pos = db.query(Position).filter_by(id=position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    pos_status = cast(PositionStatus, pos.status)
    if not can_transition(pos_status, PositionStatus.CLOSED):
        raise HTTPException(status_code=409, detail=f"Invalid transition from {pos_status}")

    pos.status = PositionStatus.CLOSED
    pos.exit_price = payload.exit_price
    pos.exit_ts = payload.exit_ts or _now()
    pos.pnl_bps = payload.pnl_bps
    pos.version += 1

    if pos.pnl_bps is not None:
        notional = (
            float(cast(float, pos.notional_usd))
            if pos.notional_usd is not None
            else float(cast(float, pos.size))
        )
        update_account_on_close(
            db,
            strategy_id=cast(str, pos.strategy_id),
            pnl_bps=float(pos.pnl_bps),
            notional=float(notional),
            exit_ts=cast(datetime, pos.exit_ts),
        )

    if settings.guardrail_enabled and pos.exit_ts and pos.pnl_bps is not None:
        update_guardrail_on_close(
            db,
            strategy_id=cast(str, pos.strategy_id),
            pair=cast(str, pos.pair),
            exit_ts=cast(datetime, pos.exit_ts),
            pnl_bps=float(pos.pnl_bps),
        )

    db.add(
        PositionEvent(
            position_id=cast(str, pos.id), event_type="CLOSED", payload=_payload_json(payload)
        )
    )
    db.commit()
    db.refresh(pos)
    cache_invalidate_position(cast(str, pos.id))
    log_event(logger, "position_closed", position_id=cast(str, pos.id))
    return pos


@app.get("/guardrail/{strategy_id}/{pair:path}", response_model=GuardrailStateResponse)
def guardrail_status(strategy_id: str, pair: str, db: Session = Depends(get_db)):
    state = get_guardrail_state(db, strategy_id, pair)
    if state is None:
        return {
            "strategy_id": strategy_id,
            "pair": pair,
            "loss_streak": 0,
            "pause_until": None,
            "can_trade": True,
            "cooldown_remaining_s": None,
        }
    allowed, pause_until, loss_streak = is_trade_allowed(db, strategy_id, pair)
    cooldown_remaining = None
    if pause_until is not None:
        cooldown_remaining = max(int((pause_until - _now()).total_seconds()), 0)
    return {
        "strategy_id": strategy_id,
        "pair": pair,
        "loss_streak": loss_streak,
        "pause_until": pause_until,
        "can_trade": allowed,
        "cooldown_remaining_s": cooldown_remaining,
    }


@app.get("/guardrail/paused", response_model=list[GuardrailPausedResponse])
def guardrail_paused(strategy_id: str | None = None, db: Session = Depends(get_db)):
    now = _now()
    query = db.query(GuardrailState).filter(
        GuardrailState.pause_until.is_not(None),
        GuardrailState.pause_until > now,
    )
    if strategy_id:
        query = query.filter(GuardrailState.strategy_id == strategy_id)
    rows = query.all()
    results: list[GuardrailPausedResponse] = []
    for row in rows:
        pause_until = cast(datetime, row.pause_until)
        cooldown_remaining = max(int((pause_until - now).total_seconds()), 0)
        results.append(
            GuardrailPausedResponse(
                strategy_id=cast(str, row.strategy_id),
                pair=cast(str, row.pair),
                loss_streak=cast(int, row.loss_streak),
                pause_until=pause_until,
                cooldown_remaining_s=cooldown_remaining,
            )
        )
    return results


@app.get("/risk/{strategy_id}", response_model=AccountStateResponse)
def risk_status(strategy_id: str, db: Session = Depends(get_db)):
    state = get_or_create_account_state(db, strategy_id)
    return state


@app.post("/risk/{strategy_id}/reset", response_model=AccountStateResponse)
def risk_reset(strategy_id: str, db: Session = Depends(get_db)):
    state = reset_account_halt(db, strategy_id)
    db.commit()
    db.refresh(state)
    return state


@app.post("/risk/{strategy_id}/halt", response_model=AccountStateResponse)
def risk_halt(
    strategy_id: str, payload: RiskHaltRequest | None = None, db: Session = Depends(get_db)
):
    state = get_or_create_account_state(db, strategy_id)
    state.halted = True
    state.halt_reason = payload.reason if payload and payload.reason else "manual_halt"
    db.commit()
    db.refresh(state)
    RISK_HALTS.labels(strategy_id=strategy_id, reason="manual_halt").inc()
    return state


@app.post("/risk/{strategy_id}/resume", response_model=AccountStateResponse)
def risk_resume(strategy_id: str, db: Session = Depends(get_db)):
    state = reset_account_halt(db, strategy_id)
    db.commit()
    db.refresh(state)
    return state


@app.post("/positions/{position_id}/cancel", response_model=PositionResponse)
def cancel_position(position_id: str, db: Session = Depends(get_db)):
    pos = db.query(Position).filter_by(id=position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    pos_status = cast(PositionStatus, pos.status)
    if not can_transition(pos_status, PositionStatus.CANCELLED):
        raise HTTPException(status_code=409, detail=f"Invalid transition from {pos_status}")

    pos.status = PositionStatus.CANCELLED
    pos.version += 1
    db.add(
        PositionEvent(
            position_id=cast(str, pos.id),
            event_type="CANCELLED",
            payload={"ts": _now().isoformat()},
        )
    )
    db.commit()
    db.refresh(pos)
    cache_invalidate_position(cast(str, pos.id))
    return pos


@app.post("/orders", response_model=OrderResponse)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    pos = db.query(Position).filter_by(id=payload.position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    order = Order(
        position_id=payload.position_id,
        order_type=payload.order_type,
        qty=payload.qty,
        price=payload.price,
        slippage_bps=payload.slippage_bps,
        status=OrderStatus.NEW,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter_by(id=order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/orders", response_model=list[OrderResponse])
def list_orders(position_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Order)
    if position_id:
        q = q.filter_by(position_id=position_id)
    return q.order_by(Order.created_at.desc()).all()
