from __future__ import annotations

"""Broker-neutral account risk management: limits evaluation, trade guard, and allocator."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


class ReservationState(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ReservationResult:
    reservation_id: str
    state: ReservationState
    reason: str | None = None


@dataclass(frozen=True)
class EntryGateDecision:
    allowed: bool
    reason: str | None
    global_utilization: float | None = None


class ReservationStateMachine:
    """Validates account-risk reservation lifecycle transitions."""

    VALID_TRANSITIONS: dict[ReservationState, set[ReservationState]] = {
        ReservationState.PENDING: {
            ReservationState.OPEN,
            ReservationState.RELEASED,
            ReservationState.EXPIRED,
        },
        ReservationState.OPEN: {
            ReservationState.CLOSED,
            ReservationState.RELEASED,
        },
        ReservationState.CLOSED: set(),
        ReservationState.RELEASED: set(),
        ReservationState.EXPIRED: set(),
    }
    VALID_INITIAL_STATES = {ReservationState.PENDING, ReservationState.OPEN}

    @classmethod
    def normalize(cls, raw: str | ReservationState) -> ReservationState:
        if isinstance(raw, ReservationState):
            return raw
        try:
            return ReservationState(str(raw).upper())
        except ValueError as exc:
            raise ValueError(f"unknown reservation state: {raw}") from exc

    @classmethod
    def validate_initial(cls, state: str | ReservationState) -> ReservationState:
        normalized = cls.normalize(state)
        if normalized not in cls.VALID_INITIAL_STATES:
            raise ValueError(f"invalid initial reservation state: {normalized.value}")
        return normalized

    @classmethod
    def validate_transition(
        cls,
        current: str | ReservationState,
        target: str | ReservationState,
    ) -> ReservationState:
        current_state = cls.normalize(current)
        target_state = cls.normalize(target)
        if target_state not in cls.VALID_TRANSITIONS[current_state]:
            raise ValueError(
                f"invalid reservation transition {current_state.value} -> {target_state.value}"
            )
        return target_state


@dataclass(frozen=True)
class AccountRiskBuffers:
    daily_loss_buffer_pct: float
    max_loss_buffer_pct: float


@dataclass(frozen=True)
class AccountRiskCostGate:
    trade_cost_gate_mode: str
    commission_round_turn_pips: float
    slippage_floor_pips: float
    min_edge_buffer_pips: float
    max_cost_to_barrier_ratio: float
    require_account_snapshot: bool
    replay_round_trip_cost_pips: float
    replay_slippage_floor_pips: float


@dataclass(frozen=True)
class AccountRiskAllocator:
    allocator_enabled: bool
    allocator_budget_fraction_daily: float
    allocator_budget_fraction_max: float
    allocator_min_headroom_buffer_ccy: float
    allocator_reserve_pending: bool
    allocator_reserve_open: bool
    allocator_priority: str


@dataclass(frozen=True)
class AccountRiskProfile:
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
    buffers: AccountRiskBuffers
    cost_gate: AccountRiskCostGate
    allocator: AccountRiskAllocator


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


def load_account_risk_profile(path: Path, profile_id: str | None = None) -> AccountRiskProfile:
    if not path.exists():
        raise FileNotFoundError(f"Account risk rules not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Account risk rules root must be mapping: {path}")
    profiles = raw.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError(f"Account risk profiles must be mapping: {path}")
    chosen_id = str(profile_id or raw.get("default_profile_id", "")).strip()
    if not chosen_id:
        raise ValueError("Account risk profile id missing (no explicit id and no default_profile_id)")
    if chosen_id not in profiles:
        raise ValueError(f"Account risk profile not found: {chosen_id}")
    cfg = profiles[chosen_id]
    if not isinstance(cfg, dict):
        raise ValueError(f"Account risk profile must be mapping: {chosen_id}")
    buffers = cfg.get("internal_buffers", {}) or {}
    cost_gate = cfg.get("cost_gate", {}) or {}
    allocator = cfg.get("allocator", {}) or {}
    return AccountRiskProfile(
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
        buffers=AccountRiskBuffers(
            daily_loss_buffer_pct=float(buffers.get("daily_loss_buffer_pct", 0.0)),
            max_loss_buffer_pct=float(buffers.get("max_loss_buffer_pct", 0.0)),
        ),
        cost_gate=AccountRiskCostGate(
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
        allocator=AccountRiskAllocator(
            allocator_enabled=bool(allocator.get("allocator_enabled", True)),
            allocator_budget_fraction_daily=float(allocator.get("allocator_budget_fraction_daily", 1.0)),
            allocator_budget_fraction_max=float(allocator.get("allocator_budget_fraction_max", 1.0)),
            allocator_min_headroom_buffer_ccy=float(allocator.get("allocator_min_headroom_buffer_ccy", 25.0)),
            allocator_reserve_pending=bool(allocator.get("allocator_reserve_pending", True)),
            allocator_reserve_open=bool(allocator.get("allocator_reserve_open", True)),
            allocator_priority=str(allocator.get("allocator_priority", "net_edge_first")),
        ),
    )


def evaluate_account_risk_limits(
    profile: AccountRiskProfile,
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
            "ACCOUNT_RISK_SNAPSHOT_MISSING"
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
        reason = "ACCOUNT_RISK_MAX_LOSS_LIMIT_BREACH"
    elif daily_loss_used >= profile.daily_loss_limit:
        reason = "ACCOUNT_RISK_DAILY_LOSS_LIMIT_BREACH"
    elif max_loss_used >= max_loss_limit_internal:
        reason = "ACCOUNT_RISK_MAX_LOSS_BUFFER_BREACH"
    elif daily_loss_used >= daily_loss_limit_internal:
        reason = "ACCOUNT_RISK_DAILY_LOSS_BUFFER_BREACH"

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
    profile: AccountRiskProfile,
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
            "block_reason": str(account_eval.get("block_reason") or "ACCOUNT_RISK_BLOCKED"),
            "hard_block_reason": str(account_eval.get("block_reason") or "ACCOUNT_RISK_BLOCKED"),
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
        gate_reason = "ACCOUNT_RISK_COST_VIABILITY_FAIL"
    elif cost_ratio > profile.cost_gate.max_cost_to_barrier_ratio:
        gate_reason = "ACCOUNT_RISK_COST_RATIO_BREACH"
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


# ─── Account Risk Decision Engine (from decision_engine.py consolidation) ───

_DISABLED_ACCOUNT_RISK_EVAL: dict[str, Any] = {
    "enabled": False,
    "profile_id": None,
    "allow_trading": True,
    "block_reason": None,
    "snapshot_available": False,
    "trading_day_id": None,
}


def evaluate_account_risk_decision(
    profile: AccountRiskProfile | None,
    state_reader: Any | None,  # AccountRiskStateReader Protocol
    symbol: str,
    now_utc: datetime,
    enabled: bool = True,
) -> dict[str, Any]:
    """Evaluate account-level risk limits from read-only runtime state.

    This consolidates the AccountRiskDecisionEngine.evaluate() logic.

    Args:
        profile: AccountRiskProfile or None
        state_reader: Object implementing AccountRiskStateReader Protocol
        symbol: Trading symbol
        now_utc: Current UTC time
        enabled: Whether account risk evaluation is active

    Returns:
        Dict with account risk evaluation results
    """
    if (not enabled) or profile is None or state_reader is None:
        return dict(_DISABLED_ACCOUNT_RISK_EVAL)

    sym = str(symbol).upper().strip()
    latest = state_reader.get_latest_account_risk_snapshot(sym)
    if latest is None:
        latest = state_reader.get_latest_account_risk_snapshot(None)

    day_id = trading_day_id(
        now_utc,
        timezone_name=profile.daily_reset_timezone,
        reset_hour=profile.daily_reset_hour,
        reset_minute=profile.daily_reset_minute,
    )
    if latest is None:
        eval_out = evaluate_account_risk_limits(
            profile,
            balance=None,
            equity=None,
            day_start_balance=None,
        )
        eval_out["enabled"] = True
        eval_out["profile_id"] = profile.profile_id
        eval_out["trading_day_id"] = day_id
        return eval_out

    since = _as_utc(now_utc) - timedelta(days=3)
    snaps = state_reader.get_account_risk_snapshots_since(since_ts=since, symbol=sym)
    if not snaps:
        snaps = state_reader.get_account_risk_snapshots_since(since_ts=since, symbol=None)

    day_start_balance = _get_day_start_balance(snaps, latest, profile, now_utc)
    eval_out = evaluate_account_risk_limits(
        profile,
        balance=float(latest["balance"]),
        equity=float(latest["equity"]),
        day_start_balance=day_start_balance,
    )
    eval_out["enabled"] = True
    eval_out["profile_id"] = profile.profile_id
    eval_out["trading_day_id"] = day_id
    return eval_out


def _get_day_start_balance(
    snapshots: list[dict[str, Any]],
    latest: dict[str, Any],
    profile: AccountRiskProfile,
    now_utc: datetime,
) -> float:
    """Get the account balance at the start of the current trading day.

    Looks through recent snapshots to find the first one on the current trading day.

    Args:
        snapshots: List of account risk snapshots
        latest: Most recent snapshot
        profile: Account risk profile (for timezone/reset time)
        now_utc: Current UTC time

    Returns:
        Balance at start of current trading day, or latest balance if not found
    """
    day_id = trading_day_id(
        now_utc,
        timezone_name=profile.daily_reset_timezone,
        reset_hour=profile.daily_reset_hour,
        reset_minute=profile.daily_reset_minute,
    )
    for row in snapshots:
        row_day = trading_day_id(
            row["snapshot_ts"],
            timezone_name=profile.daily_reset_timezone,
            reset_hour=profile.daily_reset_hour,
            reset_minute=profile.daily_reset_minute,
        )
        if row_day == day_id:
            return float(row["balance"])
    return float(latest["balance"])


def _as_utc(ts: datetime) -> datetime:
    """Ensure datetime is in UTC timezone."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
