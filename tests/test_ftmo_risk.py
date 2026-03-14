from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from src.behemoth.risk.ftmo import (
    evaluate_account_limits,
    evaluate_trade_guard,
    load_ftmo_profile,
    trading_day_id,
)


def _rules_path() -> Path:
    return Path("configs/research/governance/ftmo/ftmo_rules.yaml")


def test_load_ftmo_profile_default():
    prof = load_ftmo_profile(_rules_path())
    assert prof.profile_id == "ftmo_10k_challenge_2step"
    assert prof.initial_balance == 10000.0
    assert prof.daily_loss_limit == 500.0
    assert prof.max_loss_limit == 1000.0
    assert prof.allocator.allocator_enabled is True
    assert prof.allocator.allocator_priority == "net_edge_first"


def test_account_limits_missing_snapshot_blocks_when_required():
    prof = load_ftmo_profile(_rules_path())
    out = evaluate_account_limits(
        prof,
        balance=None,
        equity=None,
        day_start_balance=None,
    )
    assert out["allow_trading"] is False
    assert out["block_reason"] == "FTMO_ACCOUNT_SNAPSHOT_MISSING"


def test_account_limits_buffer_breach():
    prof = load_ftmo_profile(_rules_path())
    out = evaluate_account_limits(
        prof,
        balance=10000.0,
        equity=9550.0,  # 450 daily drawdown against 500 hard limit
        day_start_balance=10000.0,
    )
    assert out["allow_trading"] is False
    assert out["block_reason"] == "FTMO_DAILY_LOSS_BUFFER_BREACH"


def test_trade_guard_cost_viability():
    prof = load_ftmo_profile(_rules_path())
    account_eval = evaluate_account_limits(
        prof,
        balance=10000.0,
        equity=10000.0,
        day_start_balance=10000.0,
    )
    out = evaluate_trade_guard(
        prof,
        account_eval=account_eval,
        pred_prob=0.60,
        threshold_exec=0.55,
        barrier_pips=2.0,
        cost_est_pips=1.5,
    )
    assert out["allow_trade"] is True
    assert out["block_reason"] is None
    assert out["trade_cost_gate_mode"] == "warn"
    assert out["would_block_under_trade_cost_gate"] is True
    assert out["trade_cost_gate_block_reason"] in {"FTMO_COST_VIABILITY_FAIL", "FTMO_COST_RATIO_BREACH"}


def test_trade_guard_cost_viability_enforced():
    prof = replace(
        load_ftmo_profile(_rules_path()),
        cost_gate=replace(load_ftmo_profile(_rules_path()).cost_gate, trade_cost_gate_mode="enforce"),
    )
    account_eval = evaluate_account_limits(
        prof,
        balance=10000.0,
        equity=10000.0,
        day_start_balance=10000.0,
    )
    out = evaluate_trade_guard(
        prof,
        account_eval=account_eval,
        pred_prob=0.60,
        threshold_exec=0.55,
        barrier_pips=2.0,
        cost_est_pips=1.5,
    )
    assert out["allow_trade"] is False
    assert out["block_reason"] in {"FTMO_COST_VIABILITY_FAIL", "FTMO_COST_RATIO_BREACH"}


def test_trading_day_id():
    day = trading_day_id(
        ts_utc=datetime(2026, 3, 6, 12, 0, 0, tzinfo=timezone.utc),
        timezone_name="Europe/Prague",
        reset_hour=0,
        reset_minute=0,
    )
    assert isinstance(day, str)
    assert len(day) == 10
