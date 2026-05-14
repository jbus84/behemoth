#!/usr/bin/env python3
"""Lightweight health monitor for the JForex async tick path.

Polls the Prometheus metrics endpoint, evaluates worker health thresholds,
and emits real-time terminal output plus a persistent JSONL log.
Never kills the JForex process.
"""

import argparse
import json
import signal
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
        metric_name = name_labels[:name_labels.find("{")].replace("behemoth_worker_", "").replace("queue_", "")
        out[symbol][metric_name] = value
    return dict(out)


def evaluate_symbol(sample: dict[str, float | int], *, threshold_depth: int = DEFAULT_DEPTH_THRESHOLD, threshold_age_ms: int = DEFAULT_AGE_THRESHOLD_MS) -> str:
    """Evaluate a single sample. Returns OK / WARN / CRITICAL."""
    depth = sample.get("depth", 0)
    age_ms = sample.get("age_ms", 0)
    fatal = sample.get("fatal_total", 0)
    if fatal > 0:
        return "CRITICAL"
    if depth > threshold_depth or age_ms > threshold_age_ms:
        return "WARN"
    return "OK"


def summarize_window(samples: list[dict], *, threshold_depth: int = DEFAULT_DEPTH_THRESHOLD, threshold_age_ms: int = DEFAULT_AGE_THRESHOLD_MS) -> str:
    """Return WARN only if >= 2 of the last N samples breach thresholds."""
    if not samples:
        return "OK"
    breaches = 0
    for s in samples:
        if s.get("depth", 0) > threshold_depth or s.get("age_ms", 0) > threshold_age_ms:
            breaches += 1
    return "WARN" if breaches >= 2 else "OK"


def build_log_line(ts: str, symbol: str, sample: dict, status: str) -> dict:
    return {
        "ts": ts,
        "symbol": symbol,
        "depth": sample.get("depth", 0),
        "age_ms": sample.get("age_ms", 0),
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
            d = s.get("depth", 0)
            a = s.get("age_ms", 0)
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
