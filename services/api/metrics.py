from __future__ import annotations

import time
from typing import Callable

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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
