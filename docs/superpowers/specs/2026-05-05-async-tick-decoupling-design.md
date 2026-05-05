# Async Tick Decoupling Design

**Date:** 2026-05-05
**Topic:** Decouple JForex tick ingestion from blocking HTTP I/O by moving all Python-API calls to a per-symbol worker thread.
**Status:** Design approved; pending implementation plan.

---

## 1. Problem & Goals

**Problem.** The Dukascopy strategy thread is single-threaded and filters any tick that is >1s old or not among the last 3 per instrument (onTick-execution-policy). Today `BehemothJForexStrategy.onTick` calls `BehemothStrategyCore.onTick` synchronously, which on a full batch issues a blocking HTTP `/ticks` call and on bar completion a blocking `/predict` call, plus up to two 250ms retry sleeps. Any of these can push the strategy thread past 1s and trigger Dukascopy-side tick filtering. Live-vs-parquet capture shows a 4–13% per-symbol deficit consistent with this mechanism.

**Goal.** `onTick` returns in microseconds, never makes network calls, never sleeps. All HTTP I/O moves to a worker thread per symbol with an unbounded FIFO queue. No tick is ever dropped client-side.

**Non-goals.** Rewriting the Python ingestion API. Changing the parquet baseline or Stage 15 drift design. Adding a disk-backed queue (truly unbounded in-memory is fine for our scale).

---

## 2. Architecture & Thread Model

Two physical threads per symbol, one queue, no additional locks:

1. **Strategy thread** (Dukascopy callback thread)
   - `onTick(ITick, Instrument)` enqueues a `TickEvent` onto the symbol's `LinkedTransferQueue` and returns immediately.
   - No HTTP, no sleep, no heavy computation. Time inside `onTick` is microseconds.
   - Retains a volatile `lastEnqueueTimestamp` for health checks.

2. **Worker thread** (one per symbol, named `behemoth-worker-<symbol>`)
   - Owns an unbounded `LinkedTransferQueue<TickEvent>`.
   - Batches dequeues (drain up to N ticks or wait for next tick) to amortize queue overhead.
   - Maintains the tick-bar builder. On bar completion: blocking `/ticks` upload, then blocking `/predict`.
   - Executes prediction actions (`OPEN_MARKET`, `CLOSE_MARKET`) inline via `IEngine.submitOrder` on this same thread. Ordering is trivial — actions are processed in the order Python returns them.
   - Retries use the existing capped 250 ms backoff.

3. **Shared-state rule**
   - The worker thread is the sole writer to bar-state, position-cache, and `lastPredictedScanId` for its symbol.
   - The strategy thread only writes to the queue. No extra locks beyond the queue's own memory barrier.

4. **Tester / surrogate parity**
   - Live and tester use the same `SymbolWorker` class.
   - Test harness calls `symbolWorker.drain()` after each injected tick. This blocks until the worker has processed all queued ticks and any resulting orders. Determinism is restored by the harness, not by a separate code path.
   - `JForexTesterRunner` and `LocalJForexTesterRunner` each gain one `drain()` call per tick injection.

---

## 3. Queue Contract & Event Shapes

**TickEvent** (immutable, small — carries only what's needed for batching):

```java
record TickEvent(
    long epochMs,       // tick time (ms since epoch)
    double bid,
    double ask,
    long receiveTimeNs  // System.nanoTime() at enqueue; used for queue-age metric
) {}
```

**Batching rule on the worker thread**

The worker drains the queue with this loop:

```java
while (running) {
    List<TickEvent> batch = new ArrayList<>();
    TickEvent first = queue.take();          // block if empty
    batch.add(first);
    queue.drainTo(batch, MAX_BATCH - 1);     // grab everything waiting, up to MAX_BATCH-1
    processBatch(batch);                     // build bars, maybe trigger predict
}
```

`MAX_BATCH` is large (e.g., 1000–2000) because ticks are tiny objects and we want to amortize queue overhead. A single 1000-tick bar is ~1–5 seconds of market time for EURUSD, so one `take()` + `drainTo()` per bar is typical.

**Why `LinkedTransferQueue`**

- Unbounded, lock-free, low allocation for producer-consumer.
- `drainTo()` lets us grab the whole backlog in one shot.
- Java 21+ optimized; no blocking on the producer side.

**Queue-depth / age metric**

- `queue.size()` polled by a scheduled health thread (or JMX) every second.
- `queueAgeMs = (System.nanoTime() - batch.get(0).receiveTimeNs()) / 1_000_000` on each drain. Logged if > 50 ms.
- Prometheus gauge: `behemoth_worker_queue_age_ms{symbol="EURUSD"}`.

**Unbounded policy**

No upper bound, no `offer()` / `poll()` timeout. If the worker falls behind, the queue grows. Detection, not prevention:

- Alert fires when `queue_age_ms > 5000` for 30 s → worker starvation or Python API down.
- Alert fires when `queue_size > 100_000` for 30 s → memory pressure, possible OOM.

---

## 4. Error Handling & Backpressure

**HTTP call failures on the worker thread**

`/ticks` and `/predict` use the existing retry logic (up to 2 retries, 250 ms backoff). The difference is that retries no longer block the strategy thread; they only delay the worker's next batch.

- **Permanent failure after retries** (e.g., Python API returns 5xx or connection refused):
  - Log error with `scan_id`.
  - Drop the batch's bar state (do not advance `lastBarTimestamp`). This means the next batch of ticks will rebuild the same incomplete bar. This is safe because tick bars are built from raw ticks, not from aggregated bar state.
  - Worker continues; queue keeps draining. The same bar will be retried on next completion.
  - If Python API is down for > 30 s, queue-age alert fires and human intervenes.

- **Transient failure** (e.g., 429, timeout):
  - Retry inline with existing backoff. No special handling.

**Order-submission failure on the worker thread**

`IEngine.submitOrder` can throw `JFException`. Today this is caught in `triggerPrediction` on the strategy thread. After decoupling:

- Catch in the worker thread, log with `scan_id`, increment `behemoth_order_submit_failures_total`.
- Do not retry orders at the Java layer; the Python `/predict` response is idempotent only for the same `scan_id`, and we do not re-issue predictions for the same bar.
- A failed `OPEN_MARKET` means the position was not opened; the next bar's `CLOSE_MARKET` will be a no-op (existing `closePosition` already checks `hasOpenPosition`). This is acceptable.

**Backpressure: none**

The queue is unbounded. The only backpressure signal is the queue-age gauge. If the worker cannot keep up, ticks accumulate. This is intentional — missing a tick is worse than memory growth, and 1000-tick bars give the worker ~1–5 s per predict cycle, which is ample headroom.

**Worker crash / uncaught exception**

- Worker thread runs inside a `try/catch(Throwable)` at the top of its loop.
- On any unexpected exception: log fatal, increment `behemoth_worker_fatal_total`, signal shutdown latch.
- The strategy thread's `onTick` continues enqueueing (queue grows) but no processing occurs. Queue-age alert fires immediately.
- Live runner can be configured to restart the worker thread, but initial implementation will simply halt and alert.

**Thread lifecycle**

- `SymbolWorker.start()` on strategy init.
- `SymbolWorker.stop()` on strategy stop / destroy. `stop()` sets `running = false` and interrupts the worker. The worker drains remaining queue items, flushes any pending bar via a final `/predict` call (best-effort), then exits.

---

## 5. Observability & Metrics

**New metrics (Prometheus, emitted from the worker thread)**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `behemoth_worker_queue_depth` | Gauge | `symbol` | Queue size at poll time |
| `behemoth_worker_queue_age_ms` | Gauge | `symbol` | Age (ms) of oldest tick in queue at drain |
| `behemoth_worker_batch_size` | Histogram | `symbol` | Number of ticks per drain batch |
| `behemoth_worker_drain_duration_ms` | Histogram | `symbol` | Time from `take()` to batch completion |
| `behemoth_worker_http_predict_duration_ms` | Histogram | `symbol` | Wall time for `/predict` call |
| `behemoth_worker_http_ticks_duration_ms` | Histogram | `symbol` | Wall time for `/ticks` call |
| `behemoth_worker_tick_to_predict_ms` | Histogram | `symbol` | `epochMs` of bar-completing tick to first byte of `/predict` response |
| `behemoth_worker_fatal_total` | Counter | `symbol` | Uncaught exceptions on worker thread |
| `behemoth_order_submit_duration_ms` | Histogram | `symbol`, `action` | `IEngine.submitOrder` wall time |

**Retained metrics (existing, now emitted from worker thread)**

- `behemoth_predicted_total`, `behemoth_order_submitted_total` — same semantics, different thread source.
- `behemoth_http_errors_total` — same retry classification.

**Removed / changed**

- Existing `behemoth_onTick_duration_ms` histogram is split:
  - `behemoth_strategy_thread_onTick_ns` — nanoseconds inside `onTick` (should be < 1 µs).
  - `behemoth_worker_drain_duration_ms` — replaces the old end-to-end onTick duration.

**Alerts**

| Alert | Condition | Severity |
|-------|-----------|----------|
| `BehemothWorkerQueueStalled` | `queue_age_ms > 5000` for 30 s | Critical |
| `BehemothWorkerQueueDeep` | `queue_size > 100_000` for 30 s | Warning |
| `BehemothWorkerFatal` | `worker_fatal_total` increases | Critical |
| `BehemothOrderSubmitSlow` | `order_submit_duration_ms > 2000` for 60 s | Warning |
| `BehemothTickToPredictSlow` | `tick_to_predict_ms > 10000` for 60 s | Warning |

**Tracing**

- Each `TickEvent` carries `receiveTimeNs`. This is not propagated to Python; it is only for Java-side queue-age calculation.
- `scan_id` remains the trace key across Java → Python → Java.

---

## 6. Testing Strategy

**Unit tests (new, `src/jforex/src/test/java/com/behemoth/jforex/worker/`)**

- `SymbolWorkerTest` — mock `IEngine` and `IContext`, inject ticks via `enqueue()`, call `drain()`, assert bar builder state and order submissions.
- `TickEventTest` — immutability, nanoTime monotonicity.
- `QueueBatchingTest` — verifies `drainTo()` batch sizes, ordering, and that no tick is dropped.

**Integration tests (existing runners, modified)**

- `LocalJForexTesterRunner` — after each `onTick()` injection, calls `symbolWorker.drain()`. Asserts that all ticks are processed and orders match the deterministic baseline. This proves the async machinery behaves identically to the old sync path when fully synchronized.
- `JForexTesterRunner` — same drain semantics, but against the real JForex API (used in Stage 14).

**Regression / parity tests**

- Run the existing `make stage13-dukascopy-cert` and `make stage14-jforex-cert` suites. The only expected change is that `behemoth_strategy_thread_onTick_ns` replaces the old onTick duration metric. Order counts, `scan_id` sequences, and position states must be byte-identical to the sync baseline.
- Parquet-vs-live capture (Stage 15 prep) should show zero client-side tick drops; the 4–13% deficit should move to a Dukascopy-side metric (which we cannot change, but can now measure cleanly).

**Load / stress test**

- `SymbolWorkerStressTest` — enqueue 1_000_000 synthetic ticks at 10× normal rate, assert queue never rejects, worker keeps up, no `OutOfMemoryError`. Verify `queue_age_ms` stays < 100 ms under normal load.

**Failure-injection test**

- Mock `IEngine` that throws `JFException` on every 10th `submitOrder`. Assert worker survives, queue drains, and `behemoth_order_submit_failures_total` increments correctly.
- Mock `HttpClient` that returns 500 on `/predict`. Assert worker retries, drops bar state, and reprocesses on next batch.

---

## 7. Migration Plan

**Phase 1 — Scaffold `SymbolWorker` (no behavior change)**

1. Create `SymbolWorker` class with `LinkedTransferQueue<TickEvent>`, `start()`, `stop()`, `enqueue()`, `drain()`.
2. Wire it into `BehemothStrategyCore` behind a flag `useAsyncWorker = false`.
3. When `false`, `onTick` calls `symbolWorker.enqueue()` then immediately `symbolWorker.drain()`, so the old sync path still executes all logic inline. This proves plumbing is correct without changing behavior.
4. Run unit tests and `LocalJForexTesterRunner` parity suite. All must pass.

**Phase 2 — Move bar builder & HTTP to worker**

1. Move `TickBarBuilder` state and `triggerPrediction` call from strategy thread into `SymbolWorker.processBatch()`.
2. Set `useAsyncWorker = true` in live config.
3. In tester config, keep `useAsyncWorker = true` but add `drain()` after each tick (Section 6).
4. Run full test suite + Stage 13 + Stage 14. Order counts and `scan_id` sequence must match baseline exactly.

**Phase 3 — Cutover & cleanup**

1. Remove `useAsyncWorker` flag and the sync fallback. The async path is the only path.
2. Delete `BehemothStrategyCore.onTick` synchronous bar-building code (now lives in `SymbolWorker`).
3. Update `AGENTS.md` section 4 to document the new thread model and metrics.
4. Regenerate docs contract and mkdocs build.

**Rollback plan**

If Phase 2 shows unexpected divergence in Stage 14:
- Revert to Phase 1 scaffolding (`useAsyncWorker = false`) in one commit.
- Diagnose from worker metrics and logs without affecting live tick processing.

---

## 8. Spec Self-Review

- **Placeholder scan:** No TBD, TODO, or incomplete sections.
- **Internal consistency:** Thread model (Section 2) matches queue contract (Section 3) and error handling (Section 4). Metrics (Section 5) are derivable from the batching loop and `TickEvent` fields.
- **Scope check:** This is a single Java-side refactor. No Python API changes, no parquet changes, no broker-adapter changes beyond `IEngine.submitOrder` thread relocation.
- **Ambiguity check:** `MAX_BATCH` is a tunable constant, not fixed, to allow load-test tuning. `drain()` in tester mode is defined as "blocks until worker has processed all queued ticks and any resulting orders."

---

*End of design document.*
