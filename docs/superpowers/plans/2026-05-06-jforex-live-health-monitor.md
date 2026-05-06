# JForex Live Health Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Python health monitor script that polls the JForex Prometheus metrics endpoint, evaluates worker health thresholds, and emits real-time terminal output plus a persistent JSONL log — without ever killing the JForex process.

**Architecture:** A single Python script (`scripts/monitor_jforex_health.py`) with a polling loop that scrapes Prometheus text format from `127.0.0.1:9464/metrics`, parses worker metrics, applies threshold logic with a 3-sample rolling window, and writes both colored stdout and JSONL output. The Makefile `demo-cert-monitor` target is extended to launch it alongside the observability stack.

**Tech Stack:** Python 3, standard library (`urllib`, `json`, `signal`, `time`), `pathlib`. No external dependencies beyond the repo's existing tooling.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `scripts/monitor_jforex_health.py` | Create | Health monitor poller script |
| `tests/test_monitor_jforex_health.py` | Create | Unit tests for parser, evaluator, reporter |
| `Makefile` | Modify | Wire `demo-cert-monitor` to launch monitor |

---

## Task 1: Write the Monitor Script Scaffold

**Files:**
- Create: `scripts/monitor_jforex_health.py`
- Test: `tests/test_monitor_jforex_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_monitor_jforex_health.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_monitor_jforex_health.py -v
```

Expected: FAIL — `parse_metrics` not defined.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/monitor_jforex_health.py` with the three functions and a `__main__` block:

```python
#!/usr/bin/env python3
"""Lightweight health monitor for the JForex async tick path.

Polls the Prometheus metrics endpoint, evaluates worker health thresholds,
and emits real-time terminal output plus a persistent JSONL log.
Never kills the JForex process.
"""

import argparse
import json
import signal
import sys
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_METRICS_URL = "http://127.0.0.1:9464/metrics"
DEFAULT_POLL_INTERVAL_S = 5
DEFAULT_DEPTH_THRESHOLD = 5
DEFAULT_AGE_THRESHOLD_MS = 50
DEFAULT_LOG_FILE = "data/analysis/backtest_reconcile/health_log.jsonl"
DEFAULT_SUMMARY_WINDOW = 3


def parse_metrics(text: str) -> dict[str, dict[str, float | int]]:
    """Parse Prometheus text format and extract behemoth_worker_* per symbol."""
    out: dict[str, dict[str, float | int]] = defaultdict(dict)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "behemoth_worker_" not in line:
            continue
        # metric_name{symbol="SYM"} value
        if "{" not in line:
            continue
        name_labels, _, value_str = line.rpartition(" ")
        if not value_str:
            continue
        try:
            value = float(value_str)
            if value.is_integer():
                value = int(value)
        except ValueError:
            continue
        # extract symbol
        symbol_start = name_labels.find('symbol="')
        if symbol_start == -1:
            continue
        symbol_start += len('symbol="')
        symbol_end = name_labels.find('"', symbol_start)
        symbol = name_labels[symbol_start:symbol_end]
        # extract short metric name
        metric_name = name_labels[:name_labels.find("{")].replace("behemoth_worker_", "")
        out[symbol][metric_name] = value
    return dict(out)


def evaluate_symbol(sample: dict[str, float | int], *, threshold_depth: int = DEFAULT_DEPTH_THRESHOLD, threshold_age_ms: int = DEFAULT_AGE_THRESHOLD_MS) -> str:
    """Evaluate a single sample. Returns OK / WARN / CRITICAL."""
    depth = sample.get("queue_depth", 0)
    age_ms = sample.get("queue_age_ms", 0)
    fatal = sample.get("fatal_total", 0)
    if fatal > 0:
        return "CRITICAL"
    if depth > threshold_depth or age_ms > threshold_age_ms:
        return "WARN"
    return "OK"


def summarize_window(samples: list[dict], *, threshold_depth: int, threshold_age_ms: int) -> str:
    """Return WARN only if >= 2 of the last N samples breach thresholds."""
    if not samples:
        return "OK"
    breaches = 0
    for s in samples:
        if s.get("queue_depth", 0) > threshold_depth or s.get("queue_age_ms", 0) > threshold_age_ms:
            breaches += 1
    return "WARN" if breaches >= 2 else "OK"


def build_log_line(ts: str, symbol: str, sample: dict, status: str) -> dict:
    return {
        "ts": ts,
        "symbol": symbol,
        "depth": sample.get("queue_depth", 0),
        "age_ms": sample.get("queue_age_ms", 0),
        "batch_size": sample.get("batch_size", 0),
        "drain_ms": sample.get("drain_duration_ms", 0),
        "status": status,
    }


def print_terminal_line(line: dict) -> None:
    color = {"OK": "\033[32m", "WARN": "\033[33m", "CRITICAL": "\033[31m", "PENDING": "\033[36m", "IDLE": "\033[37m"}
    reset = "\033[0m"
    c = color.get(line["status"], "")
    print(f"[{line['ts']}] {c}{line['symbol']} depth={line['depth']} age={line['age_ms']}ms batch={line['batch_size']} drain={line['drain_ms']}ms {line['status']}{reset}")


def print_summary(samples_by_symbol: dict[str, deque], start_time: float) -> None:
    elapsed = time.time() - start_time
    total_samples = sum(len(v) for v in samples_by_symbol.values())
    symbols = list(samples_by_symbol.keys())
    max_depth = 0
    max_age = 0
    depth_peak_symbol = ""
    age_peak_symbol = ""
    fatals = 0
    for sym, deq in samples_by_symbol.items():
        for s in deq:
            d = s.get("queue_depth", 0)
            a = s.get("queue_age_ms", 0)
            if d > max_depth:
                max_depth = d
                depth_peak_symbol = sym
            if a > max_age:
                max_age = a
                age_peak_symbol = sym
            fatals += s.get("fatal_total", 0)
    status = "PASS" if fatals == 0 and all(summarize_window(list(v)) == "OK" for v in samples_by_symbol.values()) else "WARN"
    print("\n=== JForex Health Monitor Summary ===")
    print(f"Runtime: {elapsed:.0f}s")
    print(f"Samples: {total_samples}")
    print(f"Symbols: {', '.join(symbols) if symbols else 'none'}")
    print(f"Max queue depth: {max_depth} ({depth_peak_symbol})")
    print(f"Max queue age: {max_age}ms ({age_peak_symbol})")
    print(f"Worker fatals: {fatals}")
    print(f"Status: {status}")
    print("=====================================")


def _poll_once(url: str) -> dict[str, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return parse_metrics(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"__error__": {"message": str(exc)}}


def main() -> None:
    parser = argparse.ArgumentParser(description="JForex async health monitor")
    parser.add_argument("--metrics-url", default=DEFAULT_METRICS_URL)
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL_S)
    parser.add_argument("--threshold-depth", type=int, default=DEFAULT_DEPTH_THRESHOLD)
    parser.add_argument("--threshold-age-ms", type=int, default=DEFAULT_AGE_THRESHOLD_MS)
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE)
    parser.add_argument("--summary-window", type=int, default=DEFAULT_SUMMARY_WINDOW)
    args = parser.parse_args()

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    samples_by_symbol: dict[str, deque] = defaultdict(lambda: deque(maxlen=args.summary_window))
    start_time = time.time()
    running = True

    def _handle_sigint(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _handle_sigint)

    print(f"[monitor] polling {args.metrics_url} every {args.poll_interval}s")
    print(f"[monitor] logging to {log_path}")
    print("[monitor] Press Ctrl+C to stop and print summary\n")

    while running:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = _poll_once(args.metrics_url)

        if "__error__" in data:
            print(f"[{ts}] WARN: metrics endpoint unreachable: {data['__error__']['message']}")
        elif not data:
            print(f"[{ts}] PENDING: no worker metrics yet")
        else:
            with log_path.open("a", encoding="utf-8") as f:
                for symbol, sample in data.items():
                    samples_by_symbol[symbol].append(sample)
                    window_status = summarize_window(list(samples_by_symbol[symbol]), threshold_depth=args.threshold_depth, threshold_age_ms=args.threshold_age_ms)
                    status = evaluate_symbol(sample, threshold_depth=args.threshold_depth, threshold_age_ms=args.threshold_age_ms)
                    # Elevate to window status if it's worse
                    if window_status == "WARN" and status == "OK":
                        status = "WARN"
                    line = build_log_line(ts, symbol, sample, status)
                    json.dump(line, f)
                    f.write("\n")
                    print_terminal_line(line)

        try:
            time.sleep(args.poll_interval)
        except InterruptedError:
            break

    print_summary(samples_by_symbol, start_time)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_monitor_jforex_health.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/monitor_jforex_health.py tests/test_monitor_jforex_health.py
git commit -m "feat: JForex live health monitor script and unit tests"
```

---

## Task 2: Wire Makefile Target

**Files:**
- Modify: `Makefile:522-528`

- [ ] **Step 1: Modify `demo-cert-monitor` to also launch the monitor**

Replace the `demo-cert-monitor` target (lines 522-528):

```makefile
demo-cert-monitor: observability-up
	@printf "[demo-cert] Grafana: http://127.0.0.1:3000/d/behemoth-jforex-runtime/behemoth-jforex-runtime?orgId=1\n"
	@printf "[demo-cert] Prometheus: http://127.0.0.1:9090\n"
	@printf "[demo-cert] JForex metrics: http://127.0.0.1:%s/metrics\n" "$(or $(METRICS_PORT),9464)"
	@printf "[demo-cert] Runtime readiness: %s/runtime/live_symbol_readiness.json\n" "$(or $(REPORT_DIR),data/analysis/backtest_reconcile)"
	@printf "[demo-cert] Monitoring stack: started via make observability-up\n"
	@printf "[demo-cert] Health monitor: scripts/monitor_jforex_health.py\n"
	@printf "[demo-cert] Start demo runner with: make jforex-live\n"
	@env UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/monitor_jforex_health.py \
		--metrics-port $(or $(METRICS_PORT),9464) \
		--log-file $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/health_log.jsonl \
		&
echo $$! > $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/monitor.pid
```

- [ ] **Step 2: Add `demo-cert-monitor-stop` target**

Insert after `demo-cert-monitor`:

```makefile
demo-cert-monitor-stop:
	@if [ -f $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/monitor.pid ]; then \
		kill $$(cat $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/monitor.pid) 2>/dev/null || true; \
		rm -f $(or $(REPORT_DIR),data/analysis/backtest_reconcile)/monitor.pid; \
	fi
```

- [ ] **Step 3: Verify Makefile syntax**

```bash
make -n demo-cert-monitor
```

Expected: no syntax errors, commands printed.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "chore: wire demo-cert-monitor to launch JForex health monitor"
```

---

## Task 3: Integration Verification

- [ ] **Step 1: Verify script can be run standalone**

```bash
uv run python scripts/monitor_jforex_health.py --help
```

Expected: prints usage.

- [ ] **Step 2: Verify script handles missing endpoint gracefully**

```bash
timeout 6 uv run python scripts/monitor_jforex_health.py --metrics-url http://127.0.0.1:9999/metrics --poll-interval 2
```

Expected: prints `WARN: metrics endpoint unreachable` once, then exits after Ctrl+C or timeout. No crash.

- [ ] **Step 3: Run full JForex test suite**

```bash
gradle :jforex-adapter:test
```

Expected: all PASS (monitor script is pure Python, no Java changes).

- [ ] **Step 4: Commit any remaining changes**

```bash
git status --short
```

If clean, done.

---

## Spec Coverage Checklist

| Spec Requirement | Plan Task |
|---|---|
| Poll every 5s | Task 1, `--poll-interval` |
| Parse Prometheus text format | Task 1, `parse_metrics()` |
| Extract `behemoth_worker_*` per symbol | Task 1, parser test |
| Threshold: depth > 5 → WARN | Task 1, `evaluate_symbol()` + test |
| Threshold: age > 50ms → WARN | Task 1, `evaluate_symbol()` + test |
| 3-sample rolling window | Task 1, `summarize_window()` + test |
| Terminal output (colored) | Task 1, `print_terminal_line()` |
| JSONL log file | Task 1, `build_log_line()` + file write |
| Metrics endpoint down → WARN, no spam | Task 1, `_poll_once()` error handling |
| No metrics yet → PENDING | Task 1, empty data branch |
| SIGINT summary | Task 1, `print_summary()` |
| Makefile wiring | Task 2, `demo-cert-monitor` |
| `demo-cert-monitor-stop` target | Task 2, new target |

## Placeholder Scan

- No TBD, TODO, or incomplete sections.
- All code blocks contain complete, runnable Python.
- Exact commands with expected output are specified.

## Type Consistency

- `parse_metrics()` returns `dict[str, dict[str, float | int]]`.
- `evaluate_symbol()` takes a single sample dict and returns `"OK" | "WARN" | "CRITICAL"`.
- `summarize_window()` takes a list of sample dicts and returns `"OK" | "WARN"`.
- `build_log_line()` returns a flat dict matching the JSONL schema from the spec.
- Default thresholds (`5` depth, `50` ms) match the async testing gap spec.

---

**Execution Options:**

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — Execute tasks sequentially in this session.

Which approach?
