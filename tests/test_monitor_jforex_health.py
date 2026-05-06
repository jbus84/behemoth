import pytest
from scripts.monitor_jforex_health import parse_metrics, evaluate_symbol, summarize_window

PROMETHEUS_SAMPLE = """
# HELP behemoth_worker_queue_depth Current queue depth per symbol
# TYPE behemoth_worker_queue_depth gauge
behemoth_worker_queue_depth{symbol="EURUSD"} 2
behemoth_worker_queue_depth{symbol="GBPUSD"} 0
# HELP behemoth_worker_queue_age_ms Age of oldest tick in queue (ms)
# TYPE behemoth_worker_queue_age_ms gauge
behemoth_worker_queue_age_ms{symbol="EURUSD"} 12
behemoth_worker_queue_age_ms{symbol="GBPUSD"} 0
"""


def test_parse_metrics_extracts_worker_series():
    result = parse_metrics(PROMETHEUS_SAMPLE)
    assert result["EURUSD"]["depth"] == 2
    assert result["EURUSD"]["age_ms"] == 12
    assert result["GBPUSD"]["depth"] == 0


def test_evaluate_symbol_ok():
    sample = {"depth": 1, "age_ms": 10, "batch_size": 1, "drain_ms": 2}
    assert evaluate_symbol(sample) == "OK"


def test_evaluate_symbol_warn_depth():
    sample = {"depth": 8, "age_ms": 10, "batch_size": 1, "drain_ms": 2}
    assert evaluate_symbol(sample) == "WARN"


def test_evaluate_symbol_warn_age():
    sample = {"depth": 1, "age_ms": 65, "batch_size": 1, "drain_ms": 2}
    assert evaluate_symbol(sample) == "WARN"


def test_summarize_window_requires_two_of_three():
    samples = [
        {"depth": 1, "age_ms": 10},
        {"depth": 1, "age_ms": 10},
        {"depth": 8, "age_ms": 60},
    ]
    assert summarize_window(samples, threshold_depth=5, threshold_age_ms=50) == "OK"
    samples[1]["age_ms"] = 65
    assert summarize_window(samples, threshold_depth=5, threshold_age_ms=50) == "WARN"
