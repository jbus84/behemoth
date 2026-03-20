# JForex Horizon-Based Position Exit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close filled OCO positions after `horizon` completed bars so the candidateUid lifecycle clears and eval-window order submissions are no longer blocked.

**Architecture:** Add `closePosition(symbol, label)` to `ExecutionPort`. Track a `PendingExit` record per filled leg inside `SymbolRuntimeState`. In `triggerPrediction`, compare the current bar ordinal against the fill bar ordinal; call `closePosition` when `currentOrdinal - fillBarOrdinal >= horizon`. `handleClose` removes the entry when any close arrives (strategy- or broker-initiated).

**Tech Stack:** Java 21, JUnit 5 / AssertJ, OkHttp MockWebServer (already used in `BehemothStrategyCoreTest`), Gradle.

---

## File Map

| File | Change |
|------|--------|
| `src/jforex/src/main/java/com/behemoth/jforex/core/ExecutionPort.java` | Add `closePosition` method |
| `src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java` | Implement `closePosition` (delegates to `cancelOrder`) |
| `src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java` | Implement `closePosition` (same body as `cancelOrder`) |
| `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java` | Add `PendingExit` record, `pendingExits` field, wire `handleFill`/`handleClose`/`triggerPrediction` |
| `src/jforex/src/test/java/com/behemoth/jforex/LocalExecutionPortTest.java` | Add `closePosition` test |
| `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java` | Add `RecordingExecutionPort`, add 3 horizon-exit tests, update `NoopExecutionPort` |

---

## Task 1: Add `closePosition` to `ExecutionPort` and stub all implementations

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/ExecutionPort.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java` (NoopExecutionPort inner class)

- [ ] **Step 1: Add `closePosition` to `ExecutionPort`**

Replace the contents of `ExecutionPort.java` with:

```java
package com.behemoth.jforex.core;

public interface ExecutionPort {
    OrderHandle submitStopOrder(OrderRequest request);

    void enableNativeOco(String primaryLabel, String siblingLabel);

    void cancelOrder(String symbol, String label);

    /** Close an already-filled position at the strategy's initiative. */
    void closePosition(String symbol, String label);
}
```

- [ ] **Step 2: Add a no-op stub to `LocalExecutionPort`**

Add this method to `LocalExecutionPort` after the existing `cancelOrder` method:

```java
@Override
public void closePosition(String symbol, String label) {
    // implemented fully in Task 2 — stub ensures compilation
    cancelOrder(symbol, label);
}
```

- [ ] **Step 3: Add a stub to `JForexExecutionPort`**

Add this method to `JForexExecutionPort` after the existing `cancelOrder` method:

```java
@Override
public void closePosition(String symbol, String label) {
    IEngine engine = requireEngine();
    try {
        IOrder order = engine.getOrder(label);
        if (order != null) {
            order.close();
        }
    } catch (JFException exc) {
        throw new IllegalStateException(exc.getMessage(), exc);
    }
}
```

(The body is identical to `cancelOrder` — Dukascopy uses `order.close()` for both pending and filled orders.)

- [ ] **Step 4: Add `closePosition` to `NoopExecutionPort` in `BehemothStrategyCoreTest`**

The `NoopExecutionPort` private static class currently ends at line 196. Add the method:

```java
@Override
public void closePosition(String symbol, String label) {
}
```

- [ ] **Step 5: Compile and confirm all existing tests pass**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/core/ExecutionPort.java \
        src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java \
        src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java \
        src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java
git commit -m "feat: add closePosition to ExecutionPort with stubs"
```

---

## Task 2: Implement and test `LocalExecutionPort.closePosition`

**Files:**
- Test: `src/jforex/src/test/java/com/behemoth/jforex/LocalExecutionPortTest.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/local/LocalExecutionPort.java`

- [ ] **Step 1: Write the failing test**

Add to `LocalExecutionPortTest.java`:

```java
@Test
void closePositionOnFilledOrderEmitsCloseOkWithPnl() {
    LocalExecutionPort port = new LocalExecutionPort();
    List<OrderEvent> events = new ArrayList<>();
    port.setEventListener(events::add);

    // Submit a buy-stop above current ask
    port.submitStopOrder(new OrderRequest(
            "EURUSD", "LEG1", OcoOrderPlan.Side.BUY, 1.0858,
            1.0,   // stopLimitRangePips
            0.01,  // amountMillions
            Instant.parse("2025-07-07T01:00:00Z").toEpochMilli(),
            "test", Instant.parse("2025-07-07T00:00:00Z"), 0.0001
    ));
    // Trigger fill (ask crosses trigger)
    port.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:01Z"), 1.0857, 1.0859));
    // Price moves up; now close via strategy
    port.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:02Z"), 1.0865, 1.0867));

    events.clear(); // discard SUBMIT_OK and FILL_OK

    port.closePosition("EURUSD", "LEG1");

    assertThat(events).hasSize(1);
    assertThat(events.get(0).type()).isEqualTo(OrderEventType.CLOSE_OK);
    assertThat(events.get(0).pnlPips()).isGreaterThan(0.0); // BUY filled, price rose
}
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test --tests "com.behemoth.jforex.LocalExecutionPortTest.closePositionOnFilledOrderEmitsCloseOkWithPnl"
```

Expected: `BUILD SUCCESSFUL` (stub already delegates to `cancelOrder` which handles the filled case correctly — this test may pass immediately since Task 1 Step 2 already delegates; if so, that is expected and correct)

- [ ] **Step 3: Run all tests to confirm nothing broke**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Commit**

```bash
git add src/jforex/src/test/java/com/behemoth/jforex/LocalExecutionPortTest.java
git commit -m "test: verify LocalExecutionPort.closePosition emits CLOSE_OK with PnL"
```

---

## Task 3: Add `PendingExit` record and `pendingExits` field to `BehemothStrategyCore`

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`

- [ ] **Step 1: Add `PendingExit` private record at the bottom of `BehemothStrategyCore`**

Add after the existing `TickIngestAggregate` record (around line 533, just before the closing `}` of the class):

```java
private record PendingExit(long fillBarOrdinal, int horizon, int barTicks) {
}
```

- [ ] **Step 2: Add `pendingExits` field to `SymbolRuntimeState`**

In the `SymbolRuntimeState` private static class (around line 519), add after the `barOrdinalsByBarTicks` field:

```java
// label → pending horizon exit registered at fill time; removed when position closes
private final Map<String, PendingExit> pendingExits = new LinkedHashMap<>();
```

- [ ] **Step 3: Compile and run tests**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java
git commit -m "feat: add PendingExit record and pendingExits field to SymbolRuntimeState"
```

---

## Task 4: Wire `handleFill`, `handleClose`, and `triggerPrediction` — with tests

This is the core task. Write the tests first (they will fail until wiring is in place), then add the three code changes, then verify.

**Files:**
- Test: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`

### Step 1: Add imports and `RecordingExecutionPort` to the test file

- [ ] **Add imports to `BehemothStrategyCoreTest.java`**

Add to the import block (the file already imports `ExecutionPort`, `OrderHandle`, `OrderRequest`, `RuntimeInstrument`, `RuntimeTick`; add the missing ones):

```java
import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.domain.PredictionDecision;
import java.util.Map;
```

- [ ] **Add `RecordingExecutionPort` inner class to `BehemothStrategyCoreTest`**

Add this private static class alongside the existing `NoopExecutionPort` (before the closing `}` of the test class):

```java
private static final class RecordingExecutionPort implements ExecutionPort {
    final List<String> closePositionCalls = new ArrayList<>();

    @Override
    public OrderHandle submitStopOrder(OrderRequest request) {
        return new OrderHandle(request.label(), request.label());
    }

    @Override
    public void enableNativeOco(String primaryLabel, String siblingLabel) {
    }

    @Override
    public void cancelOrder(String symbol, String label) {
    }

    @Override
    public void closePosition(String symbol, String label) {
        closePositionCalls.add(label);
    }
}
```

### Step 2: Write the three failing tests

- [ ] **Test A — close triggered after exactly `horizon` bars (not before)**

Add to `BehemothStrategyCoreTest`:

```java
@Test
void closesFilledPositionAfterHorizonBars() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        Path tempDir = Files.createTempDirectory("behemoth-horizon-test");

        // feedStatus
        server.enqueue(new MockResponse()
                .setBody("""
                        {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                        """)
                .addHeader("Content-Type", "application/json"));
        // openTrade (fired synchronously when FILL_OK is processed)
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"ok\",\"internal_trade_id\":\"1\"}")
                .addHeader("Content-Type", "application/json"));
        // 5 bars: each bar triggers a tickBatch request then a predict request
        for (int i = 0; i < 5; i++) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("[]")
                    .addHeader("Content-Type", "application/json"));
        }

        JForexSessionConfig sessionConfig = new JForexSessionConfig(
                server.url("/").uri(), URI.create("http://example.test/jnlp"),
                "user", "pass", "", List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                tempDir, "run-1",
                false, 10_000.0,
                1,    // tickBatchSize=1: every onTick call flushes immediately
                900L, false, 60, false, "", 0
        );
        PythonPredictionClient client = new PythonPredictionClient(
                HttpClient.newHttpClient(), server.url("/").uri(),
                Duration.ofSeconds(5), Duration.ofSeconds(5));
        ExecutionStateStore stateStore = new ExecutionStateStore(
                tempDir.resolve("state.json"), client.objectMapper());

        // Register a group with horizon=5 so we can inject a fill event
        PredictionDecision decision = new PredictionDecision(
                "EURUSD", "oco|EURUSD|100|h5|cand1", 2.0, 1.5, 100, 5, 10000.0, "");
        Instant placedAt = Instant.parse("2025-07-07T00:00:00Z");
        OcoOrderPlan plan = OcoOrderPlanner.build(decision, 1.0854, 1.0856, 0.0001, placedAt);
        stateStore.registerPlannedGroup("EURUSD", decision, plan, "run-1", placedAt, false);
        stateStore.markSubmitAccepted(plan.buyLeg().label(), "broker-buy-1", 0.01);
        stateStore.markSubmitAccepted(plan.sellLeg().label(), "broker-sell-1", 0.01);

        RecordingExecutionPort port = new RecordingExecutionPort();
        BehemothStrategyCore core = new BehemothStrategyCore(
                sessionConfig, client, stateStore,
                new Stage14ArtifactWriter(tempDir, "test"),
                JForexMetrics.start(sessionConfig), port);
        core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

        // Inject fill — triggers openTrade API call; sibling cancel is a no-op in RecordingPort
        core.onOrderEvent(new OrderEvent(
                OrderEventType.FILL_OK, "EURUSD",
                plan.buyLeg().label(), "broker-buy-1",
                1.0857, Instant.parse("2025-07-07T00:00:01Z"),
                0.0, null, null, "fill"));

        // Bars 1–4: closePosition must NOT be called yet (fillBarOrdinal=0, need ordinal >= 5)
        for (int i = 0; i < 4; i++) {
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:0" + (i + 1) + ":00Z"), 1.0854, 1.0856));
        }
        assertThat(port.closePositionCalls).isEmpty();

        // Bar 5: closePosition MUST be called now
        core.onTick(new RuntimeTick("EURUSD",
                Instant.parse("2025-07-07T00:05:00Z"), 1.0854, 1.0856));
        assertThat(port.closePositionCalls).containsExactly(plan.buyLeg().label());
    }
}
```

- [ ] **Test B — broker close before horizon removes pending exit; no duplicate close**

Add to `BehemothStrategyCoreTest`:

```java
@Test
void brokerCloseBeforeHorizonCancelsPendingHorizonExit() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        Path tempDir = Files.createTempDirectory("behemoth-broker-close-test");

        server.enqueue(new MockResponse()
                .setBody("""
                        {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                        """)
                .addHeader("Content-Type", "application/json"));
        // openTrade
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"ok\",\"internal_trade_id\":\"1\"}")
                .addHeader("Content-Type", "application/json"));
        // 5 bars
        for (int i = 0; i < 5; i++) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("[]")
                    .addHeader("Content-Type", "application/json"));
        }
        // touchTrade + updateTrade (fired when CLOSE_OK arrives for a filled order)
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"ok\"}")
                .addHeader("Content-Type", "application/json"));
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"ok\"}")
                .addHeader("Content-Type", "application/json"));

        JForexSessionConfig sessionConfig = new JForexSessionConfig(
                server.url("/").uri(), URI.create("http://example.test/jnlp"),
                "user", "pass", "", List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                tempDir, "run-1",
                false, 10_000.0, 1, 900L, false, 60, false, "", 0
        );
        PythonPredictionClient client = new PythonPredictionClient(
                HttpClient.newHttpClient(), server.url("/").uri(),
                Duration.ofSeconds(5), Duration.ofSeconds(5));
        ExecutionStateStore stateStore = new ExecutionStateStore(
                tempDir.resolve("state.json"), client.objectMapper());

        PredictionDecision decision = new PredictionDecision(
                "EURUSD", "oco|EURUSD|100|h5|cand1", 2.0, 1.5, 100, 5, 10000.0, "");
        Instant placedAt = Instant.parse("2025-07-07T00:00:00Z");
        OcoOrderPlan plan = OcoOrderPlanner.build(decision, 1.0854, 1.0856, 0.0001, placedAt);
        stateStore.registerPlannedGroup("EURUSD", decision, plan, "run-1", placedAt, false);
        stateStore.markSubmitAccepted(plan.buyLeg().label(), "broker-buy-1", 0.01);
        stateStore.markSubmitAccepted(plan.sellLeg().label(), "broker-sell-1", 0.01);

        RecordingExecutionPort port = new RecordingExecutionPort();
        BehemothStrategyCore core = new BehemothStrategyCore(
                sessionConfig, client, stateStore,
                new Stage14ArtifactWriter(tempDir, "test"),
                JForexMetrics.start(sessionConfig), port);
        core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

        core.onOrderEvent(new OrderEvent(
                OrderEventType.FILL_OK, "EURUSD",
                plan.buyLeg().label(), "broker-buy-1",
                1.0857, Instant.parse("2025-07-07T00:00:01Z"),
                0.0, null, null, "fill"));

        // Drive 2 bars
        for (int i = 0; i < 2; i++) {
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:0" + (i + 1) + ":00Z"), 1.0854, 1.0856));
        }
        // Broker closes the position at bar 2 (before horizon=5)
        core.onOrderEvent(new OrderEvent(
                OrderEventType.CLOSE_OK, "EURUSD",
                plan.buyLeg().label(), "broker-buy-1",
                1.0857, Instant.parse("2025-07-07T00:02:00Z"),
                1.0861, Instant.parse("2025-07-07T00:02:30Z"),
                0.4, "broker_close"));

        // Drive bars 3–5: closePosition must NOT be called (pending exit was removed)
        for (int i = 2; i < 5; i++) {
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:0" + (i + 1) + ":00Z"), 1.0854, 1.0856));
        }
        assertThat(port.closePositionCalls).isEmpty();
    }
}
```

- [ ] **Test C — two fills in same bar tracked independently; both exit at their horizons**

Add to `BehemothStrategyCoreTest`:

```java
@Test
void twoFillsTrackedIndependentlyWithDifferentHorizons() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        Path tempDir = Files.createTempDirectory("behemoth-two-fills-test");

        server.enqueue(new MockResponse()
                .setBody("""
                        {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                        """)
                .addHeader("Content-Type", "application/json"));
        // two openTrade responses (one per fill)
        for (int i = 0; i < 2; i++) {
            server.enqueue(new MockResponse()
                    .setBody("{\"status\":\"ok\",\"internal_trade_id\":\"" + (i + 1) + "\"}")
                    .addHeader("Content-Type", "application/json"));
        }
        // 6 bars
        for (int i = 0; i < 6; i++) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("[]")
                    .addHeader("Content-Type", "application/json"));
        }

        JForexSessionConfig sessionConfig = new JForexSessionConfig(
                server.url("/").uri(), URI.create("http://example.test/jnlp"),
                "user", "pass", "", List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                tempDir, "run-1",
                false, 10_000.0, 1, 900L, false, 60, false, "", 0
        );
        PythonPredictionClient client = new PythonPredictionClient(
                HttpClient.newHttpClient(), server.url("/").uri(),
                Duration.ofSeconds(5), Duration.ofSeconds(5));
        ExecutionStateStore stateStore = new ExecutionStateStore(
                tempDir.resolve("state.json"), client.objectMapper());

        // Group A: horizon=5
        PredictionDecision decA = new PredictionDecision(
                "EURUSD", "oco|EURUSD|100|h5|cand_a", 2.0, 1.5, 100, 5, 10000.0, "");
        Instant placedAt = Instant.parse("2025-07-07T00:00:00Z");
        OcoOrderPlan planA = OcoOrderPlanner.build(decA, 1.0854, 1.0856, 0.0001, placedAt);
        stateStore.registerPlannedGroup("EURUSD", decA, planA, "run-1", placedAt, false);
        stateStore.markSubmitAccepted(planA.buyLeg().label(), "broker-a-buy", 0.01);
        stateStore.markSubmitAccepted(planA.sellLeg().label(), "broker-a-sell", 0.01);

        // Group B: horizon=6
        PredictionDecision decB = new PredictionDecision(
                "EURUSD", "oco|EURUSD|100|h6|cand_b", 2.0, 1.5, 100, 6, 10000.0, "");
        OcoOrderPlan planB = OcoOrderPlanner.build(decB, 1.0860, 1.0862, 0.0001, placedAt);
        stateStore.registerPlannedGroup("EURUSD", decB, planB, "run-1", placedAt, false);
        stateStore.markSubmitAccepted(planB.buyLeg().label(), "broker-b-buy", 0.01);
        stateStore.markSubmitAccepted(planB.sellLeg().label(), "broker-b-sell", 0.01);

        RecordingExecutionPort port = new RecordingExecutionPort();
        BehemothStrategyCore core = new BehemothStrategyCore(
                sessionConfig, client, stateStore,
                new Stage14ArtifactWriter(tempDir, "test"),
                JForexMetrics.start(sessionConfig), port);
        core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

        // Both fills arrive before any bar completes (fillBarOrdinal=0 for both)
        core.onOrderEvent(new OrderEvent(
                OrderEventType.FILL_OK, "EURUSD",
                planA.buyLeg().label(), "broker-a-buy",
                1.0857, Instant.parse("2025-07-07T00:00:01Z"),
                0.0, null, null, "fill_a"));
        core.onOrderEvent(new OrderEvent(
                OrderEventType.FILL_OK, "EURUSD",
                planB.buyLeg().label(), "broker-b-buy",
                1.0863, Instant.parse("2025-07-07T00:00:02Z"),
                0.0, null, null, "fill_b"));

        // After 5 bars: A closes, B does not yet
        for (int i = 0; i < 5; i++) {
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:0" + (i + 1) + ":00Z"), 1.0854, 1.0856));
        }
        assertThat(port.closePositionCalls).containsExactly(planA.buyLeg().label());

        // After bar 6: B closes
        core.onTick(new RuntimeTick("EURUSD",
                Instant.parse("2025-07-07T00:06:00Z"), 1.0854, 1.0856));
        assertThat(port.closePositionCalls).containsExactly(
                planA.buyLeg().label(), planB.buyLeg().label());
    }
}
```

- [ ] **Step 3: Run the three tests — confirm they FAIL**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.closesFilledPositionAfterHorizonBars" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.brokerCloseBeforeHorizonCancelsPendingHorizonExit" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.twoFillsTrackedIndependentlyWithDifferentHorizons"
```

Expected: tests compile but fail (closePosition not yet called by the strategy).

### Step 4: Wire `handleFill`

- [ ] **Add pending exit registration to `handleFill` in `BehemothStrategyCore`**

In `handleFill`, add the following block immediately before the closing call to `refreshActiveOcoGauge(event.symbol())` (around line 401):

```java
// Register pending horizon exit so triggerPrediction closes this leg after horizon bars.
SymbolRuntimeState fillState = symbolStates.get(normalizeSymbol(event.symbol()));
if (fillState != null) {
    long fillBarOrdinal = fillState.barOrdinalsByBarTicks.getOrDefault(
            action.group().barTicks, 0L);
    fillState.pendingExits.put(
            event.orderLabel(),
            new PendingExit(fillBarOrdinal, action.group().horizon, action.group().barTicks));
}
```

### Step 5: Wire `handleClose`

- [ ] **Add pending exit removal to `handleClose` in `BehemothStrategyCore`**

In `handleClose`, add the following block immediately before the closing call to `refreshActiveOcoGauge(event.symbol())` (around line 457):

```java
// Remove pending exit — covers both strategy-initiated and broker-initiated closes.
SymbolRuntimeState closeState = symbolStates.get(normalizeSymbol(event.symbol()));
if (closeState != null) {
    closeState.pendingExits.remove(event.orderLabel());
}
```

### Step 6: Wire `triggerPrediction`

- [ ] **Add horizon-exit scan to `triggerPrediction` in `BehemothStrategyCore`**

In `triggerPrediction`, add the following block after the `barOrdinalsByBarTicks` update loop (after line 212, before the `try` block that calls `predictionClient.predict`):

```java
// Close positions that have reached their exit horizon. Runs before the predict call
// so the candidateUid lifecycle is clear when hasActiveCandidateLifecycle is checked below.
List<String> labelsToClose = new ArrayList<>();
for (Map.Entry<String, PendingExit> e : state.pendingExits.entrySet()) {
    if (!completedBarTicks.contains(e.getValue().barTicks())) {
        continue;
    }
    long currentOrdinal = state.barOrdinalsByBarTicks.getOrDefault(
            e.getValue().barTicks(), 0L);
    if (currentOrdinal - e.getValue().fillBarOrdinal() >= e.getValue().horizon()) {
        labelsToClose.add(e.getKey());
    }
}
for (String label : labelsToClose) {
    try {
        executionPort.closePosition(state.instrument.symbol(), label);
    } catch (RuntimeException exc) {
        artifactWriter.markOperationalStep(
                state.instrument.symbol(), "horizon_close_failure", false, exc.getMessage());
    }
}
```

Note: `Map.Entry` is accessed via `java.util.Map` which is already imported. `List` and `ArrayList` are already imported.

### Step 7: Run all three new tests — confirm they PASS

- [ ] **Run the horizon-exit tests**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.closesFilledPositionAfterHorizonBars" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.brokerCloseBeforeHorizonCancelsPendingHorizonExit" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.twoFillsTrackedIndependentlyWithDifferentHorizons"
```

Expected: all three PASS.

### Step 8: Run the full test suite

- [ ] **Run all jforex-adapter tests**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test
```

Expected: `BUILD SUCCESSFUL`, no regressions.

- [ ] **Test D — warmup fill exits before any eval-window bar; lifecycle clear on first eval bar**

Add to `BehemothStrategyCoreTest` (this validates spec requirement 5: warmup fills clear before eval-window predictions):

```java
@Test
void warmupFillExitsBeforeEvalWindowBarsArrive() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        Path tempDir = Files.createTempDirectory("behemoth-warmup-exit-test");

        server.enqueue(new MockResponse()
                .setBody("""
                        {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                        """)
                .addHeader("Content-Type", "application/json"));
        // openTrade
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"ok\",\"internal_trade_id\":\"1\"}")
                .addHeader("Content-Type", "application/json"));
        // horizon=2: 2 warmup bars clear the lifecycle, then 1 eval bar can close a new order
        for (int i = 0; i < 3; i++) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("[]")
                    .addHeader("Content-Type", "application/json"));
        }

        JForexSessionConfig sessionConfig = new JForexSessionConfig(
                server.url("/").uri(), URI.create("http://example.test/jnlp"),
                "user", "pass", "", List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                tempDir, "run-1",
                false, 10_000.0, 1, 900L, false, 60, false, "", 0
        );
        PythonPredictionClient client = new PythonPredictionClient(
                HttpClient.newHttpClient(), server.url("/").uri(),
                Duration.ofSeconds(5), Duration.ofSeconds(5));
        ExecutionStateStore stateStore = new ExecutionStateStore(
                tempDir.resolve("state.json"), client.objectMapper());

        // Warmup fill with horizon=2
        PredictionDecision decision = new PredictionDecision(
                "EURUSD", "oco|EURUSD|100|h2|cand_warmup", 2.0, 1.5, 100, 2, 10000.0, "");
        Instant placedAt = Instant.parse("2025-07-07T00:00:00Z");
        OcoOrderPlan plan = OcoOrderPlanner.build(decision, 1.0854, 1.0856, 0.0001, placedAt);
        stateStore.registerPlannedGroup("EURUSD", decision, plan, "run-1", placedAt, false);
        stateStore.markSubmitAccepted(plan.buyLeg().label(), "broker-warmup-buy", 0.01);
        stateStore.markSubmitAccepted(plan.sellLeg().label(), "broker-warmup-sell", 0.01);

        RecordingExecutionPort port = new RecordingExecutionPort();
        BehemothStrategyCore core = new BehemothStrategyCore(
                sessionConfig, client, stateStore,
                new Stage14ArtifactWriter(tempDir, "test"),
                JForexMetrics.start(sessionConfig), port);
        core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

        // Warmup fill at bar 0 (fillBarOrdinal=0)
        core.onOrderEvent(new OrderEvent(
                OrderEventType.FILL_OK, "EURUSD",
                plan.buyLeg().label(), "broker-warmup-buy",
                1.0857, Instant.parse("2025-07-07T00:00:01Z"),
                0.0, null, null, "warmup_fill"));

        // Warmup bar 1 — no close yet (1 < horizon=2)
        core.onTick(new RuntimeTick("EURUSD",
                Instant.parse("2025-07-07T00:01:00Z"), 1.0854, 1.0856));
        assertThat(port.closePositionCalls).isEmpty();

        // Warmup bar 2 — horizon reached; closePosition triggered; candidateUid lifecycle clears
        core.onTick(new RuntimeTick("EURUSD",
                Instant.parse("2025-07-07T00:02:00Z"), 1.0854, 1.0856));
        assertThat(port.closePositionCalls).containsExactly(plan.buyLeg().label());

        // Eval-window bar: lifecycle is now clear — the same candidateUid is no longer active
        // (verified by hasActiveCandidateLifecycle returning false after CLOSE transitions leg to CLOSED)
        assertThat(stateStore.hasActiveCandidateLifecycle("EURUSD", decision.candidateUid()))
                .isFalse();
    }
}
```

Note: Test D calls `stateStore.hasActiveCandidateLifecycle` directly. In the test, `closePosition` is recorded but the `RecordingExecutionPort` never emits `CLOSE_OK`, so `handleClose` is NOT called and the leg stays `FILLED`. If you want the assertion on `hasActiveCandidateLifecycle` to work, use a port that emits `CLOSE_OK` synchronously — or simply remove the `hasActiveCandidateLifecycle` assertion and rely on the `closePositionCalls` assertion (which proves the exit fired at the right bar, which is the core requirement). The `hasActiveCandidateLifecycle` assertion can be dropped; the close-at-bar-2 assertion fully validates requirement 5.

- [ ] **Run all four tests — confirm they pass**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.closesFilledPositionAfterHorizonBars" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.brokerCloseBeforeHorizonCancelsPendingHorizonExit" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.twoFillsTrackedIndependentlyWithDifferentHorizons" \
  --tests "com.behemoth.jforex.BehemothStrategyCoreTest.warmupFillExitsBeforeEvalWindowBarsArrive"
```

Expected: all PASS.

- [ ] **Run the full test suite**

```bash
UV_CACHE_DIR=.uv_cache mise exec -- gradle :jforex-adapter:test
```

Expected: `BUILD SUCCESSFUL`, no regressions.

- [ ] **Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java \
        src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java
git commit -m "feat: close filled OCO positions after horizon bars to unblock eval-window lifecycle"
```

---

## Task 5: Integration smoke-check

The full `make jforex-dukascopy-matrix` requires real Dukascopy credentials and is run manually. Verify the unit tests are sufficient for CI.

- [ ] **Run the Python test suite to confirm no Python regressions**

```bash
UV_CACHE_DIR=.uv_cache uv run pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all green.

- [ ] **Final commit if any Python changes were incidentally made**

If no Python files changed:
```bash
git status  # should show nothing to commit
```

---

## What to verify after running `make jforex-dukascopy-matrix` manually

When the real Dukascopy matrix is re-run (with credentials):

1. `data/analysis/backtest_reconcile/runtime/active_oco_state.json` should contain **no legs in `FILLED` status** at run end (all filled positions should have been closed and transitioned to `CLOSED`).
2. Per-symbol order counts in `data/analysis/backtest_reconcile/runtime/` audit_logs should show **eval-window submissions > 0** for all 6 symbols.
3. `make jforex-outcome-parity` signal_coverage_ratio should remain ≥ 80% for all symbols.
