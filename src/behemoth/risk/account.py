from __future__ import annotations

"""Broker-neutral account risk interfaces with FTMO compatibility mappings."""

from pathlib import Path
from typing import Any

from src.behemoth.risk.ftmo import (
    FtmoAllocator,
    FtmoBuffers,
    FtmoCostGate,
    FtmoProfile,
    evaluate_account_limits,
    evaluate_trade_guard,
    load_ftmo_profile,
    trading_day_id,
)

AccountRiskBuffers = FtmoBuffers
AccountRiskCostGate = FtmoCostGate
AccountRiskAllocator = FtmoAllocator
AccountRiskProfile = FtmoProfile


def load_account_risk_profile(path: Path, profile_id: str | None = None) -> AccountRiskProfile:
    """Load the active account-risk profile from the legacy FTMO rules contract."""
    return load_ftmo_profile(path, profile_id)


def evaluate_account_risk_limits(
    profile: AccountRiskProfile,
    *,
    balance: float | None,
    equity: float | None,
    day_start_balance: float | None,
) -> dict[str, Any]:
    """Evaluate account-level risk limits using the active profile."""
    return evaluate_account_limits(
        profile,
        balance=balance,
        equity=equity,
        day_start_balance=day_start_balance,
    )


def evaluate_trade_risk_guard(
    profile: AccountRiskProfile,
    *,
    account_eval: dict[str, Any],
    pred_prob: float,
    threshold_exec: float,
    barrier_pips: float,
    cost_est_pips: float,
) -> dict[str, Any]:
    """Evaluate candidate-level admission under the active account-risk profile."""
    return evaluate_trade_guard(
        profile,
        account_eval=account_eval,
        pred_prob=pred_prob,
        threshold_exec=threshold_exec,
        barrier_pips=barrier_pips,
        cost_est_pips=cost_est_pips,
    )
