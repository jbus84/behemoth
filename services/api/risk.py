from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy.orm import Session

from .models import AccountState, Position, PositionStatus
from .settings import settings
from .weights import load_weights


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


def compute_open_exposure(db: Session, strategy_id: str) -> float:
    rows = (
        db.query(Position)
        .filter(
            Position.strategy_id == strategy_id,
            Position.status.in_(
                [PositionStatus.PENDING, PositionStatus.OPEN, PositionStatus.CLOSING]
            ),
        )
        .all()
    )
    total = 0.0
    for r in rows:
        notional = (
            float(cast(float, r.notional_usd))
            if r.notional_usd is not None
            else float(cast(float, r.size))
        )
        total += float(notional or 0.0)
    return total


def compute_target_notional(strategy_id: str, pair: str, equity: float) -> float:
    weights = load_weights(strategy_id)
    if not weights:
        return equity * settings.max_total_exposure_pct
    weight = float(weights.get(pair, 1.0))
    weight_sum = float(sum(max(v, 0.0) for v in weights.values())) or 1.0
    return equity * settings.max_total_exposure_pct * (weight / weight_sum)


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
    max_total = equity * settings.max_total_exposure_pct
    max_pair = equity * settings.max_pair_exposure_pct
    open_exposure = compute_open_exposure(db, strategy_id)

    target = compute_target_notional(strategy_id, pair, equity)
    overshoot = target * (1.0 + settings.max_weight_overshoot_pct)
    allowed = min(max_pair, overshoot)

    if open_exposure + requested_notional > max_total:
        return False, {
            "error": "max_total_exposure",
            "max_total": max_total,
            "open_exposure": open_exposure,
        }
    if requested_notional > allowed:
        return False, {
            "error": "max_pair_exposure",
            "max_allowed": allowed,
            "target_notional": target,
            "max_pair": max_pair,
        }

    return True, {
        "equity": equity,
        "target_notional": target,
        "open_exposure": open_exposure,
        "max_total": max_total,
        "max_pair": max_pair,
    }


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

    if settings.max_daily_loss_pct and daily_loss_pct <= -settings.max_daily_loss_pct:
        state.halted = True
        state.halt_reason = f"max_daily_loss {daily_loss_pct:.4f}"
    if settings.max_dd_pct and dd_pct <= -settings.max_dd_pct:
        state.halted = True
        state.halt_reason = f"max_drawdown {dd_pct:.4f}"
    if (
        settings.max_consecutive_losses
        and state.consecutive_losses >= settings.max_consecutive_losses
    ):
        state.halted = True
        state.halt_reason = f"max_consecutive_losses {state.consecutive_losses}"

    return state


def reset_account_halt(db: Session, strategy_id: str) -> AccountState:
    state = get_or_create_account_state(db, strategy_id)
    state.halted = False
    state.halt_reason = None
    state.consecutive_losses = 0
    return state
