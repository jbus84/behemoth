from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.orm import Session

from .models import AccountState, GuardrailState, Position, PositionStatus

REQUEST_COUNT = Counter(
    "behemoth_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "behemoth_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

GUARDRAIL_BLOCKS = Counter(
    "behemoth_guardrail_blocks_total",
    "Guardrail blocks on entry",
    ["strategy_id", "pair"],
)

RISK_HALTS = Counter(
    "behemoth_risk_halts_total",
    "Risk halt triggers",
    ["strategy_id", "reason"],
)

ACTIVE_POSITIONS = Gauge(
    "behemoth_positions_active_total",
    "Active positions (pending/open/closing)",
    ["strategy_id"],
)
ACTIVE_POSITIONS_BY_PAIR = Gauge(
    "behemoth_positions_active_by_pair",
    "Active positions by pair",
    ["strategy_id", "pair"],
)

GUARDRAIL_PAUSED_TOTAL = Gauge(
    "behemoth_guardrail_paused_total",
    "Pairs paused by guardrail",
    ["strategy_id"],
)
GUARDRAIL_PAUSED_BY_PAIR = Gauge(
    "behemoth_guardrail_paused_by_pair",
    "Guardrail paused flag (1 paused)",
    ["strategy_id", "pair"],
)
GUARDRAIL_PAUSE_UNTIL = Gauge(
    "behemoth_guardrail_pause_until",
    "Guardrail pause-until timestamp (unix seconds)",
    ["strategy_id", "pair"],
)
GUARDRAIL_COOLDOWN_SECONDS = Gauge(
    "behemoth_guardrail_cooldown_seconds",
    "Guardrail cooldown remaining seconds",
    ["strategy_id", "pair"],
)

ACCOUNT_EQUITY = Gauge("behemoth_account_equity", "Account equity", ["strategy_id"])
ACCOUNT_PEAK_EQUITY = Gauge("behemoth_account_peak_equity", "Account peak equity", ["strategy_id"])
ACCOUNT_DAY_START_EQUITY = Gauge(
    "behemoth_account_day_start_equity", "Account day-start equity", ["strategy_id"]
)
ACCOUNT_CONSEC_LOSSES = Gauge(
    "behemoth_account_consecutive_losses", "Account consecutive losses", ["strategy_id"]
)
ACCOUNT_HALTED = Gauge("behemoth_account_halted", "Account halted flag (1 halted)", ["strategy_id"])

SYSTEM_UP = Gauge("behemoth_api_up", "API health flag")

_active_pos_labels: set[tuple[str, str]] = set()
_active_total_labels: set[tuple[str]] = set()
_guardrail_labels: set[tuple[str, str]] = set()
_guardrail_total_labels: set[tuple[str]] = set()
_guardrail_pause_labels: set[tuple[str, str]] = set()
_guardrail_cooldown_labels: set[tuple[str, str]] = set()
_account_labels: set[tuple[str]] = set()


def track_request(method: str, path: str, status: int, duration_s: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_s)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def timeit() -> Callable[[], float]:
    start = time.perf_counter()

    def done() -> float:
        return time.perf_counter() - start

    return done


def _update_labeled_gauge(gauge: Gauge, seen: set[tuple], values: dict[tuple, float]) -> None:
    for label in list(seen - values.keys()):
        gauge.remove(*label)
        seen.discard(label)
    for label, val in values.items():
        gauge.labels(*label).set(val)
        seen.add(label)


def refresh_state_metrics(db: Session) -> None:
    SYSTEM_UP.set(1)

    active_statuses = [
        PositionStatus.PENDING,
        PositionStatus.OPEN,
        PositionStatus.CLOSING,
    ]
    active_positions = db.query(Position).filter(Position.status.in_(active_statuses)).all()

    active_by_pair: dict[tuple[str, str], float] = {}
    active_by_strategy: dict[tuple[str], float] = {}
    for pos in active_positions:
        strategy_id = str(pos.strategy_id)
        pair = str(pos.pair)
        active_by_pair[(strategy_id, pair)] = active_by_pair.get((strategy_id, pair), 0.0) + 1.0
        active_by_strategy[(strategy_id,)] = active_by_strategy.get((strategy_id,), 0.0) + 1.0

    _update_labeled_gauge(ACTIVE_POSITIONS_BY_PAIR, _active_pos_labels, active_by_pair)
    _update_labeled_gauge(ACTIVE_POSITIONS, _active_total_labels, active_by_strategy)

    now = datetime.now(timezone.utc)
    paused_by_pair: dict[tuple[str, str], float] = {}
    pause_until_by_pair: dict[tuple[str, str], float] = {}
    cooldown_by_pair: dict[tuple[str, str], float] = {}
    paused_by_strategy: dict[tuple[str], float] = {}
    for state in db.query(GuardrailState).all():
        pause_until = state.pause_until
        if pause_until is not None and pause_until > now:
            strategy_id = str(state.strategy_id)
            pair = str(state.pair)
            cooldown_remaining = max(int((pause_until - now).total_seconds()), 0)
            paused_by_pair[(strategy_id, pair)] = 1.0
            pause_until_by_pair[(strategy_id, pair)] = pause_until.timestamp()
            cooldown_by_pair[(strategy_id, pair)] = float(cooldown_remaining)
            paused_by_strategy[(strategy_id,)] = paused_by_strategy.get((strategy_id,), 0.0) + 1.0

    _update_labeled_gauge(GUARDRAIL_PAUSED_BY_PAIR, _guardrail_labels, paused_by_pair)
    _update_labeled_gauge(GUARDRAIL_PAUSED_TOTAL, _guardrail_total_labels, paused_by_strategy)
    _update_labeled_gauge(GUARDRAIL_PAUSE_UNTIL, _guardrail_pause_labels, pause_until_by_pair)
    _update_labeled_gauge(GUARDRAIL_COOLDOWN_SECONDS, _guardrail_cooldown_labels, cooldown_by_pair)

    account_values: dict[tuple[str], dict[str, float]] = {}
    for state in db.query(AccountState).all():
        strategy_id = str(state.strategy_id)
        account_values[(strategy_id,)] = {
            "equity": float(cast(float, state.equity)),
            "peak": float(cast(float, state.peak_equity)),
            "day_start": float(cast(float, state.day_start_equity)),
            "losses": float(cast(float, state.consecutive_losses)),
            "halted": 1.0 if state.halted else 0.0,
        }

    # Ensure gauges show 0 instead of "No data" when there are no active/paused positions.
    for label in account_values.keys():
        active_by_strategy.setdefault(label, 0.0)
        paused_by_strategy.setdefault(label, 0.0)

    for label, values in account_values.items():
        ACCOUNT_EQUITY.labels(*label).set(values["equity"])
        ACCOUNT_PEAK_EQUITY.labels(*label).set(values["peak"])
        ACCOUNT_DAY_START_EQUITY.labels(*label).set(values["day_start"])
        ACCOUNT_CONSEC_LOSSES.labels(*label).set(values["losses"])
        ACCOUNT_HALTED.labels(*label).set(values["halted"])
        _account_labels.add(label)

    for label in list(_account_labels - account_values.keys()):
        ACCOUNT_EQUITY.remove(*label)
        ACCOUNT_PEAK_EQUITY.remove(*label)
        ACCOUNT_DAY_START_EQUITY.remove(*label)
        ACCOUNT_CONSEC_LOSSES.remove(*label)
        ACCOUNT_HALTED.remove(*label)
        _account_labels.discard(label)
