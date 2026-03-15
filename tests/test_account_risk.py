from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.behemoth.risk.account import (
    evaluate_account_risk_limits,
    evaluate_trade_risk_guard,
    load_account_risk_profile,
    trading_day_id,
)


def _rules_path() -> Path:
    return Path("configs/research/governance/ftmo/ftmo_rules.yaml")


def test_load_account_risk_profile_uses_legacy_ftmo_contract() -> None:
    profile = load_account_risk_profile(_rules_path())
    assert profile.profile_id == "ftmo_10k_challenge_2step"
    assert profile.currency == "USD"


def test_account_risk_limits_expose_block_reason() -> None:
    profile = load_account_risk_profile(_rules_path())
    out = evaluate_account_risk_limits(
        profile,
        balance=10000.0,
        equity=9550.0,
        day_start_balance=10000.0,
    )
    assert out["allow_trading"] is False
    assert out["block_reason"] == "FTMO_DAILY_LOSS_BUFFER_BREACH"


def test_trade_risk_guard_preserves_cost_gate_behavior() -> None:
    profile = load_account_risk_profile(_rules_path())
    account_eval = evaluate_account_risk_limits(
        profile,
        balance=10000.0,
        equity=10000.0,
        day_start_balance=10000.0,
    )
    out = evaluate_trade_risk_guard(
        profile,
        account_eval=account_eval,
        pred_prob=0.60,
        threshold_exec=0.55,
        barrier_pips=2.0,
        cost_est_pips=1.5,
    )
    assert out["allow_trade"] is True
    assert out["trade_cost_gate_mode"] == "warn"


def test_trading_day_id_alias_still_available() -> None:
    day = trading_day_id(
        ts_utc=datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc),
        timezone_name="Europe/Prague",
        reset_hour=0,
        reset_minute=0,
    )
    assert day == "2026-03-06"
