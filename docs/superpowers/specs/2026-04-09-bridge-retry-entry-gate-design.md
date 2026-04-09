# Bridge Retry + Entry Gate Enforcement Design

**Date:** 2026-04-09  
**Status:** Approved

## Problem

Two related gaps in live readiness reliability:

1. **Bridge always fails on startup.** `BrokerBridgeLoader.bridge()` wraps its entire retry loop in a single `catch (Exception exc)` that immediately marks a symbol `ERROR_PAUSED`. When the Python API is still completing its lifespan at the moment JForex first calls `/ticks/batch` (a transient `IOException` / `PythonApiException(599)`), all six symbols transition `BRIDGING → ERROR_PAUSED` before the API is ready. There is no recovery path; symbols stay `ERROR_PAUSED` for the session.

2. **Entry gate is unenforceable.** `live_entries_allowed` is a Prometheus gauge wired to `SymbolRuntimeState.entriesAllowed`, but the field is set and never read. Order submission proceeds regardless of readiness state, making the metric misleading and leaving a correctness gap for genuine error conditions.

## Solution

### Fix 1 — Bridge transient retry

**File:** `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java`

Move exception handling inside the `while(true)` loop. Distinguish:

- **Transient** (`PythonApiException` with status 599 — the HTTP client's `IOException` wrapper): log via `artifactWriter.markOperationalStep(symbol, "bridge_tick_batch_transient_error", false, exc.getMessage())`, call `idlePoll()`, then continue the loop. The existing 20-minute `startupTimeout` deadline bounds total retry time — no new config.
- **Fatal** (any other exception, including Python logic errors returning 4xx/5xx): mark `ERROR_PAUSED` immediately, return `BridgeResult(false, ...)` as today.

If the deadline expires while in transient-retry, the existing timeout path fires normally with `"Broker bridge timed out..."`.

**Result:** Transient connection errors during startup are retried silently within the deadline window. Symbols reach `READY` once the API is healthy. Genuine errors still fail fast.

### Fix 2 — Wire the entry gate

**File:** `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`

In `executeActions()`, add a guard at the start of the `isOpenMarket` branch:

```java
if (!state.entriesAllowed) {
    metrics.recordEntryBlocked(action.symbol());
    artifactWriter.markOperationalStep(action.symbol(), "entry_blocked_not_ready", false,
        "entries not allowed in current readiness state");
    continue;
}
```

- Only new position opens (`isOpenMarket`) are blocked.
- Close-market actions, fill handling, and trade updates are unaffected.
- Predict still runs on every bar — Python API stays warm, thresholds continue calibrating.
- A new `recordEntryBlocked` counter is added to `JForexMetrics` (label: `symbol`) and exposed as `behemoth_jforex_entry_blocked_total`.

**Result:** When a symbol is genuinely `ERROR_PAUSED`, no new orders are submitted. The metric makes suppressed entries visible in Grafana.

## Architecture

```
BrokerBridgeLoader.bridge()
  while (!deadline) {
    try {
      tickBatch(...)          ← transient failure retries here
      if (ready) markReady()
    } catch (PythonApiException(599)) {
      logTransient(); idlePoll(); continue   ← NEW
    } catch (Exception) {
      markErrorPaused(); return              ← unchanged
    }
    if (timeout) markErrorPaused(); return  ← unchanged
  }

BehemothStrategyCore.executeActions()
  for (action : actions) {
    if (action.isOpenMarket()) {
      if (!state.entriesAllowed) { block + log; continue }  ← NEW
      submitMarketOrder(...)
    }
    ...
  }
```

## Testing

### `BrokerBridgeLoaderTest`

1. `tickBatch` throws `PythonApiException(599)` on first call, succeeds on second — assert symbol reaches `READY`, not `ERROR_PAUSED`.
2. All `tickBatch` calls return 599 until deadline — assert `ERROR_PAUSED` with `"timed out"` message (not `"failed"`).
3. `tickBatch` throws `PythonApiException(422)` — assert `ERROR_PAUSED` immediately (no retry).

### `BehemothStrategyCoreTest`

1. `setEntriesAllowed(symbol, false)` called before bar completion — assert `submitMarketOrder` is never called, assert `entry_blocked_not_ready` artifact step is recorded.
2. `setEntriesAllowed(symbol, true)` (default) — assert existing order submission behavior unchanged.

### `JForexMetrics` (inline or unit)

1. `recordEntryBlocked` increments `behemoth_jforex_entry_blocked_total` for the correct symbol label.

## Files Changed

| File | Change |
|------|--------|
| `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java` | Transient retry logic |
| `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java` | Entry gate guard in `executeActions` |
| `src/jforex/src/main/java/com/behemoth/jforex/observability/JForexMetrics.java` | `recordEntryBlocked` counter |
| `src/jforex/src/test/java/com/behemoth/jforex/live/BrokerBridgeLoaderTest.java` | Three new test cases |
| `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java` | Two new test cases |
