# JForex Live Health Monitor Design

**Date:** 2026-05-06
**Topic:** Non-intrusive health monitoring for the async tick decoupling path on the Dukascopy demo account
**Status:** Design approved; pending implementation plan.

---

## 1. Problem & Goals

**Problem.** When `make jforex-live` runs on the demo account, the async tick decoupling is active (`synchronousDrain=false`). The worker threads process ticks asynchronously, and queue health is only visible in Prometheus/Grafana. We need confidence that the worker threads keep up with real market tick rates without requiring human eyes glued to dashboards.

**Goal.** A lightweight Python script that polls the JForex metrics endpoint (`127.0.0.1:9464/metrics`) every 5 seconds, evaluates worker health thresholds, and emits both real-time terminal output and a persistent JSONL log. It never kills the JForex process — it only reports.

**Non-goals.** No new Java code. No Alertmanager changes. No metrics schema changes.

---

## 2. Architecture & Components

```
scripts/monitor_jforex_health.py    (new)
├── Scraper (every 5s, Prometheus text format)
├── Parser (extract behemoth_worker_* series)
├── Evaluator (thresholds from config)
├── TerminalReporter (colored stdout, WARN only)
└── FileReporter (JSONL to report_dir/health_log.jsonl)
```

**Metrics scraped:**
- `behemoth_worker_queue_depth{symbol="EURUSD"}` — current queue length
- `behemoth_worker_queue_age_ms{symbol="EURUSD"}` — age of oldest tick in ms
- `behemoth_worker_batch_size{symbol="EURUSD"}` — ticks processed in last batch
- `behemoth_worker_drain_duration_ms{symbol="EURUSD"}` — time to process last batch
- `behemoth_worker_fatal_total{symbol="EURUSD"}` — uncaught exceptions in worker thread

**Default thresholds:**
- `queue_depth > 5` → WARN
- `queue_age_ms > 50` → WARN
- `worker_fatal_total > 0` → CRITICAL (logged but process continues)

**Output formats:**
- **Terminal:** `[2026-05-06T14:32:01Z] EURUSD depth=0 age=2ms batch=1 drain=1ms OK`
- **JSONL:** `{"ts":"2026-05-06T14:32:01Z","symbol":"EURUSD","depth":0,"age_ms":2,"batch_size":1,"drain_ms":1,"status":"OK"}`

The script is started by `make demo-cert-monitor` alongside the observability stack.

---

## 3. Error Handling & Edge Cases

### Metrics endpoint down
If `curl` to `127.0.0.1:9464/metrics` fails, log a single WARN line, then retry next poll cycle. Don't spam.

### No worker metrics yet
If the endpoint is up but no `behemoth_worker_*` series exist (strategy hasn't started), emit `status=PENDING` and keep polling.

### Zero ticks in window
If all metrics are zero for a symbol for > 60s, the market may be closed. Log `status=IDLE` — don't treat as failure.

### High queue_age_ms spike
Use the last 3 samples (15s window) rather than a single sample to avoid GC-pause false positives. Only WARN if 2 of 3 are over threshold.

### Process lifecycle
The script handles `SIGINT` gracefully — flushes the JSONL file and prints an end-of-run summary before exiting.

**End-of-run summary (on SIGINT):**
```
=== JForex Health Monitor Summary ===
Runtime: 00:42:15
Samples: 505
Symbols: EURUSD, GBPUSD, USDJPY
Max queue depth: 3 (EURUSD @ 14:12:03)
Max queue age: 23ms (EURUSD @ 14:12:03)
Worker fatals: 0
Status: PASS
```

---

## 4. File Changes

| File | Change |
|------|--------|
| `scripts/monitor_jforex_health.py` | New: health monitor poller script |
| `Makefile` | Modify: wire `demo-cert-monitor` to also start the monitor |

---

## 5. Spec Self-Review

- **Placeholder scan:** No TBD, TODO, or incomplete sections.
- **Internal consistency:** Thresholds match the async testing gap spec (depth > 5, age > 50ms). Output formats are explicit. Process never kills JForex.
- **Scope check:** Single script + Makefile wiring. No decomposition needed.
- **Ambiguity check:** Threshold evaluation uses 3-sample window to avoid GC false positives. Summary format is explicit.

---

*End of design document.*
