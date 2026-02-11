from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy.orm import Session

from .models import AccountState
from .settings import settings


def _utc_now():
    return datetime.now(timezone.utc)


def get_or_create_account_state(db: Session, strategy_id: str) -> AccountState:
    state = db.query(AccountState).filter_by(strategy_id=strategy_id).first()
    if state is not None:
        return state
    now = _utc_now().date()
    equity = float(settings.account_equity_start)
    state = AccountState(
        strategy_id=strategy_id,
        equity=equity,
        peak_equity=equity,
        day_start_equity=equity,
        day_start_date=now,
        consecutive_losses=0,
        halted=False,
        halt_reason=None,
    )
    db.add(state)
    db.flush()
    return state


def check_risk_on_create(
    db: Session,
    strategy_id: str,
    pair: str,
    requested_notional: float,
) -> tuple[bool, dict]:
    state = get_or_create_account_state(db, strategy_id)
    if state.halted:
        return False, {"error": "risk_halted", "reason": state.halt_reason}

    equity = float(cast(float, state.equity))
    return True, {"equity": equity}


def update_account_on_close(
    db: Session,
    strategy_id: str,
    pnl_bps: float,
    notional: float,
    exit_ts: datetime,
) -> AccountState:
    state = get_or_create_account_state(db, strategy_id)
    equity_before = float(cast(float, state.equity))

    exit_date = exit_ts.date()
    if state.day_start_date != exit_date:
        state.day_start_date = exit_date
        state.day_start_equity = equity_before

    pnl_usd = float(notional) * float(pnl_bps) / 10000.0
    equity_after = equity_before + pnl_usd
    state.equity = equity_after
    state.peak_equity = max(float(cast(float, state.peak_equity)), equity_after)

    if pnl_usd <= 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0

    day_start_equity = float(cast(float, state.day_start_equity))
    peak_equity = float(cast(float, state.peak_equity))
    daily_loss_pct = (equity_after - day_start_equity) / day_start_equity
    dd_pct = (equity_after - peak_equity) / peak_equity

    if settings.max_daily_loss_pct:
        buffer = float(settings.max_daily_loss_buffer_pct or 0.0)
        limit = float(settings.max_daily_loss_pct)
        if daily_loss_pct <= -limit:
            state.halted = True
            state.halt_reason = f"max_daily_loss {daily_loss_pct:.4f}"
        elif buffer > 0 and daily_loss_pct <= -(limit - buffer):
            state.halted = True
            state.halt_reason = f"max_daily_loss_buffer {daily_loss_pct:.4f}"

    if settings.max_dd_pct:
        buffer = float(settings.max_dd_buffer_pct or 0.0)
        limit = float(settings.max_dd_pct)
        if dd_pct <= -limit:
            state.halted = True
            state.halt_reason = f"max_drawdown {dd_pct:.4f}"
        elif buffer > 0 and dd_pct <= -(limit - buffer):
            state.halted = True
            state.halt_reason = f"max_drawdown_buffer {dd_pct:.4f}"
    return state


def reset_account_halt(db: Session, strategy_id: str) -> AccountState:
    state = get_or_create_account_state(db, strategy_id)
    state.halted = False
    state.halt_reason = None
    state.consecutive_losses = 0
    return state
