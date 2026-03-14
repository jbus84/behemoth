from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


@dataclass(frozen=True)
class FtmoBuffers:
    daily_loss_buffer_pct: float
    max_loss_buffer_pct: float


@dataclass(frozen=True)
class FtmoCostGate:
    trade_cost_gate_mode: str
    commission_round_turn_pips: float
    slippage_floor_pips: float
    min_edge_buffer_pips: float
    max_cost_to_barrier_ratio: float
    require_account_snapshot: bool
    replay_round_trip_cost_pips: float
    replay_slippage_floor_pips: float


@dataclass(frozen=True)
class FtmoAllocator:
    allocator_enabled: bool
    allocator_budget_fraction_daily: float
    allocator_budget_fraction_max: float
    allocator_min_headroom_buffer_ccy: float
    allocator_reserve_pending: bool
    allocator_reserve_open: bool
    allocator_priority: str


@dataclass(frozen=True)
class FtmoProfile:
    profile_id: str
    mode: str
    currency: str
    initial_balance: float
    daily_loss_limit: float
    max_loss_limit: float
    profit_target_phase1: float
    profit_target_phase2: float
    min_trading_days: int
    daily_reset_timezone: str
    daily_reset_hour: int
    daily_reset_minute: int
    official_source_url: str
    buffers: FtmoBuffers
    cost_gate: FtmoCostGate
    allocator: FtmoAllocator


def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _normalize_trade_cost_gate_mode(raw: Any) -> str:
    mode = str(raw or "warn").strip().lower()
    if mode not in {"off", "warn", "enforce"}:
        return "warn"
    return mode


def trading_day_id(
    ts_utc: datetime,
    *,
    timezone_name: str,
    reset_hour: int,
    reset_minute: int,
) -> str:
    ts_local = _to_utc(ts_utc).astimezone(ZoneInfo(timezone_name))
    reset_local = ts_local.replace(hour=int(reset_hour), minute=int(reset_minute), second=0, microsecond=0)
    if ts_local < reset_local:
        reset_local = reset_local - timedelta(days=1)
    return reset_local.date().isoformat()


def load_ftmo_profile(path: Path, profile_id: str | None = None) -> FtmoProfile:
    if not path.exists():
        raise FileNotFoundError(f"FTMO rules not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"FTMO rules root must be mapping: {path}")
    profiles = raw.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError(f"FTMO profiles must be mapping: {path}")
    chosen_id = str(profile_id or raw.get("default_profile_id", "")).strip()
    if not chosen_id:
        raise ValueError("FTMO profile id missing (no explicit id and no default_profile_id)")
    if chosen_id not in profiles:
        raise ValueError(f"FTMO profile not found: {chosen_id}")
    cfg = profiles[chosen_id]
    if not isinstance(cfg, dict):
        raise ValueError(f"FTMO profile must be mapping: {chosen_id}")
    buffers = cfg.get("internal_buffers", {}) or {}
    cost_gate = cfg.get("cost_gate", {}) or {}
    allocator = cfg.get("allocator", {}) or {}
    return FtmoProfile(
        profile_id=chosen_id,
        mode=str(cfg.get("mode", "challenge_2step")),
        currency=str(cfg.get("currency", "USD")),
        initial_balance=float(cfg["initial_balance"]),
        daily_loss_limit=float(cfg["daily_loss_limit"]),
        max_loss_limit=float(cfg["max_loss_limit"]),
        profit_target_phase1=float(cfg.get("profit_target_phase1", 0.0)),
        profit_target_phase2=float(cfg.get("profit_target_phase2", 0.0)),
        min_trading_days=int(cfg.get("min_trading_days", 0)),
        daily_reset_timezone=str(cfg.get("daily_reset_timezone", "Europe/Prague")),
        daily_reset_hour=int(cfg.get("daily_reset_hour", 0)),
        daily_reset_minute=int(cfg.get("daily_reset_minute", 0)),
        official_source_url=str(cfg.get("official_source_url", "")),
        buffers=FtmoBuffers(
            daily_loss_buffer_pct=float(buffers.get("daily_loss_buffer_pct", 0.0)),
            max_loss_buffer_pct=float(buffers.get("max_loss_buffer_pct", 0.0)),
        ),
        cost_gate=FtmoCostGate(
            trade_cost_gate_mode=_normalize_trade_cost_gate_mode(
                cost_gate.get("trade_cost_gate_mode", "warn")
            ),
            commission_round_turn_pips=float(cost_gate.get("commission_round_turn_pips", 0.0)),
            slippage_floor_pips=float(cost_gate.get("slippage_floor_pips", 0.0)),
            min_edge_buffer_pips=float(cost_gate.get("min_edge_buffer_pips", 0.0)),
            max_cost_to_barrier_ratio=float(cost_gate.get("max_cost_to_barrier_ratio", 1.0)),
            require_account_snapshot=bool(cost_gate.get("require_account_snapshot", False)),
            replay_round_trip_cost_pips=float(
                cost_gate.get(
                    "replay_round_trip_cost_pips",
                    cost_gate.get("commission_round_turn_pips", 0.5),
                )
            ),
            replay_slippage_floor_pips=float(
                cost_gate.get("replay_slippage_floor_pips", 0.0)
            ),
        ),
        allocator=FtmoAllocator(
            allocator_enabled=bool(allocator.get("allocator_enabled", True)),
            allocator_budget_fraction_daily=float(allocator.get("allocator_budget_fraction_daily", 1.0)),
            allocator_budget_fraction_max=float(allocator.get("allocator_budget_fraction_max", 1.0)),
            allocator_min_headroom_buffer_ccy=float(allocator.get("allocator_min_headroom_buffer_ccy", 25.0)),
            allocator_reserve_pending=bool(allocator.get("allocator_reserve_pending", True)),
            allocator_reserve_open=bool(allocator.get("allocator_reserve_open", True)),
            allocator_priority=str(allocator.get("allocator_priority", "net_edge_first")),
        ),
    )


def evaluate_account_limits(
    profile: FtmoProfile,
    *,
    balance: float | None,
    equity: float | None,
    day_start_balance: float | None,
) -> dict[str, Any]:
    snapshot_available = (
        balance is not None and equity is not None and day_start_balance is not None
    )
    if not snapshot_available:
        reason = (
            "FTMO_ACCOUNT_SNAPSHOT_MISSING"
            if profile.cost_gate.require_account_snapshot
            else None
        )
        return {
            "snapshot_available": False,
            "allow_trading": reason is None,
            "block_reason": reason,
            "daily_loss_used": None,
            "max_loss_used": None,
            "daily_loss_headroom": None,
            "max_loss_headroom": None,
            "daily_loss_limit_internal": profile.daily_loss_limit * (1.0 - profile.buffers.daily_loss_buffer_pct),
            "max_loss_limit_internal": profile.max_loss_limit * (1.0 - profile.buffers.max_loss_buffer_pct),
            "daily_loss_limit_hard": profile.daily_loss_limit,
            "max_loss_limit_hard": profile.max_loss_limit,
        }

    bal = float(balance)
    eq = float(equity)
    day_bal = float(day_start_balance)

    daily_loss_used = max(0.0, day_bal - eq)
    max_loss_used = max(0.0, profile.initial_balance - eq)

    daily_loss_limit_internal = profile.daily_loss_limit * (1.0 - profile.buffers.daily_loss_buffer_pct)
    max_loss_limit_internal = profile.max_loss_limit * (1.0 - profile.buffers.max_loss_buffer_pct)

    reason: str | None = None
    if max_loss_used >= profile.max_loss_limit:
        reason = "FTMO_MAX_LOSS_LIMIT_BREACH"
    elif daily_loss_used >= profile.daily_loss_limit:
        reason = "FTMO_DAILY_LOSS_LIMIT_BREACH"
    elif max_loss_used >= max_loss_limit_internal:
        reason = "FTMO_MAX_LOSS_BUFFER_BREACH"
    elif daily_loss_used >= daily_loss_limit_internal:
        reason = "FTMO_DAILY_LOSS_BUFFER_BREACH"

    return {
        "snapshot_available": True,
        "allow_trading": reason is None,
        "block_reason": reason,
        "daily_loss_used": daily_loss_used,
        "max_loss_used": max_loss_used,
        "daily_loss_headroom": daily_loss_limit_internal - daily_loss_used,
        "max_loss_headroom": max_loss_limit_internal - max_loss_used,
        "daily_loss_limit_internal": daily_loss_limit_internal,
        "max_loss_limit_internal": max_loss_limit_internal,
        "daily_loss_limit_hard": profile.daily_loss_limit,
        "max_loss_limit_hard": profile.max_loss_limit,
        "balance": bal,
        "equity": eq,
        "day_start_balance": day_bal,
    }


def evaluate_trade_guard(
    profile: FtmoProfile,
    *,
    account_eval: dict[str, Any],
    pred_prob: float,
    threshold_exec: float,
    barrier_pips: float,
    cost_est_pips: float,
) -> dict[str, Any]:
    if not bool(account_eval.get("allow_trading", True)):
        return {
            "allow_trade": False,
            "block_reason": str(account_eval.get("block_reason") or "FTMO_ACCOUNT_BLOCKED"),
            "hard_block_reason": str(account_eval.get("block_reason") or "FTMO_ACCOUNT_BLOCKED"),
            "would_block_under_trade_cost_gate": False,
            "trade_cost_gate_block_reason": None,
            "trade_cost_gate_mode": profile.cost_gate.trade_cost_gate_mode,
            "estimated_trade_cost_pips": None,
            "expected_edge_proxy_pips": None,
            "net_viability_margin_pips": None,
            "cost_to_barrier_ratio": None,
        }

    b = max(float(barrier_pips), 1e-9)
    cost_total = (
        float(cost_est_pips)
        + profile.cost_gate.commission_round_turn_pips
        + profile.cost_gate.slippage_floor_pips
    )
    expected_edge_proxy = max(0.0, float(pred_prob)) * b
    net_margin = expected_edge_proxy - cost_total - profile.cost_gate.min_edge_buffer_pips
    cost_ratio = cost_total / b
    gate_reason: str | None = None
    if net_margin <= 0.0:
        gate_reason = "FTMO_COST_VIABILITY_FAIL"
    elif cost_ratio > profile.cost_gate.max_cost_to_barrier_ratio:
        gate_reason = "FTMO_COST_RATIO_BREACH"
    mode = _normalize_trade_cost_gate_mode(profile.cost_gate.trade_cost_gate_mode)
    effective_reason = gate_reason if (gate_reason is not None and mode == "enforce") else None

    return {
        "allow_trade": effective_reason is None,
        "block_reason": effective_reason,
        "hard_block_reason": None,
        "would_block_under_trade_cost_gate": gate_reason is not None,
        "trade_cost_gate_block_reason": gate_reason,
        "trade_cost_gate_mode": mode,
        "estimated_trade_cost_pips": cost_total,
        "expected_edge_proxy_pips": expected_edge_proxy,
        "net_viability_margin_pips": net_margin,
        "cost_to_barrier_ratio": cost_ratio,
        "pred_prob": float(pred_prob),
        "threshold_exec": float(threshold_exec),
    }
