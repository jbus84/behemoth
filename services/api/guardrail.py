from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy.orm import Session

from .models import GuardrailState
from .settings import settings


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_guardrail_state(db: Session, strategy_id: str, pair: str) -> GuardrailState | None:
    return db.query(GuardrailState).filter_by(strategy_id=strategy_id, pair=pair).first()


def is_trade_allowed(
    db: Session,
    strategy_id: str,
    pair: str,
    as_of: datetime | None = None,
) -> tuple[bool, datetime | None, int]:
    state = get_guardrail_state(db, strategy_id, pair)
    if state is None:
        return True, None, 0
    pause_until = _as_utc(cast(datetime | None, state.pause_until))
    as_of = datetime.now(timezone.utc) if as_of is None else _as_utc(as_of)
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    loss_streak = int(cast(int, state.loss_streak))
    if pause_until is not None and as_of < pause_until:
        return False, pause_until, loss_streak
    return True, pause_until, loss_streak


def update_guardrail_on_close(
    db: Session,
    strategy_id: str,
    pair: str,
    exit_ts: datetime,
    pnl_bps: float,
) -> GuardrailState:
    state = get_guardrail_state(db, strategy_id, pair)
    if state is None:
        state = GuardrailState(strategy_id=strategy_id, pair=pair, loss_streak=0)
        db.add(state)
        db.flush()

    exit_dt = _as_utc(exit_ts)
    if exit_dt is None:
        exit_dt = datetime.now(timezone.utc)
    loss_threshold = settings.guardrail_loss_threshold
    loss_streak_target = settings.guardrail_loss_streak
    cooldown_days = settings.guardrail_cooldown_days

    if pnl_bps > loss_threshold:
        state.loss_streak = 0
        state.pause_until = None
    else:
        state.loss_streak += 1
        if state.loss_streak >= loss_streak_target:
            state.pause_until = exit_dt + timedelta(days=cooldown_days)
            state.loss_streak = 0

    return state
