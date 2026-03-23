# Dukascopy Paper Trading Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-symbol Dukascopy paper-trading readiness so `make jforex-live` warms each symbol from local parquet, bridges it to near-real-time with broker history, pauses stale symbols for new entries only, and writes operator-visible readiness status.

**Architecture:** Keep `scripts/run_jforex_live.py` as a thin supervisor. Add a Java live-readiness layer under the JForex adapter that owns parquet warmup, broker bridge, per-symbol readiness state, metrics, and status-file writing. Gate new-entry submission inside `BehemothStrategyCore` so subscribed symbols can ingest ticks continuously while only `READY` symbols may open fresh positions.

**Tech Stack:** Java 21, JUnit 5, AssertJ, OkHttp MockWebServer, Dukascopy JForex API, existing FastAPI `/backfill` and `/runtime/feed/status`, Prometheus Java client.

---

## File Structure

### Existing files to modify

- `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
  - Add live-readiness config defaults and environment parsing.
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
  - Add per-symbol `entriesAllowed` gate for new orders.
- `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java`
  - Wire the live readiness coordinator into JForex callbacks.
- `src/jforex/src/main/java/com/behemoth/jforex/observability/JForexMetrics.java`
  - Add readiness/staleness gauges and state-transition counters.
- `src/jforex/src/main/java/com/behemoth/jforex/runtime/PythonPredictionClient.java`
  - Add a small helper for `/runtime/feed/status` polling if a convenience method is needed by the coordinator.
- `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
  - Extend tests for paused symbols, readiness recovery, and “pause new entries only”.

### New files to create

- `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessState.java`
  - Enum for `COLD`, `PARQUET_WARMING`, `BRIDGING`, `READY`, `STALE_PAUSED`, `ERROR_PAUSED`.
- `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessSnapshot.java`
  - Immutable per-symbol status payload.
- `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessSnapshot.java`
  - Immutable top-level status-file payload.
- `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessRegistry.java`
  - In-memory per-symbol state machine and session-level counters.
- `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessStatusWriter.java`
  - Atomic JSON writer for `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json`.
- `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java`
  - Phase-preserving local parquet tail loader for live startup.
- `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerHistoryPort.java`
  - Interface to fetch broker-side recent ticks.
- `src/jforex/src/main/java/com/behemoth/jforex/live/JForexBrokerHistoryPort.java`
  - `IHistory` implementation of `BrokerHistoryPort`.
- `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java`
  - Chunked bridge-to-now loader with per-symbol `clientTickSeq` continuity.
- `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java`
  - Orchestrates warmup, bridge, freshness checks, entry gating, metrics, and status-file writes.
- `src/jforex/src/test/java/com/behemoth/jforex/live/SymbolReadinessRegistryTest.java`
  - Unit tests for state transitions and stale/ready recovery.
- `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessStatusWriterTest.java`
  - Unit tests for JSON schema and atomic snapshot writes.
- `src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java`
  - Unit tests for `keep = 30000 + (pre_count % 100)` and phase preservation.
- `src/jforex/src/test/java/com/behemoth/jforex/live/BrokerBridgeLoaderTest.java`
  - Unit tests for chunked bridging, timeout behavior, and monotonic `clientTickSeq`.
- `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`
  - Unit tests for per-symbol readiness, stale-feed pause, and mixed-state sessions.

### Existing files to check while implementing

- `src/jforex/src/main/java/com/behemoth/jforex/local/ParquetTickLoader.java`
  - Reference for live parquet tail phase logic.
- `src/behemoth/api/server.py`
  - Confirm `/backfill` and `/runtime/feed/status` semantics, especially `last_client_tick_seq`.
- `src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/FeedStatusResponsePayload.java`
- `src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/FeedStatusSymbolPayload.java`

## Task 1: Add Live Readiness Config Surface

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
- Test: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`

- [ ] **Step 1: Write the failing config-default test**

```java
@Test
void sessionConfigExposesLiveReadinessDefaults() {
    JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false);
    assertThat(cfg.liveReadinessEnabled()).isTrue();
    assertThat(cfg.liveWarmupTicks()).isEqualTo(30_000);
    assertThat(cfg.liveLookbackDays()).isEqualTo(31);
    assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(60);
    assertThat(cfg.liveFreshnessSeconds()).isEqualTo(30);
    assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(20);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.LiveReadinessCoordinatorTest.sessionConfigExposesLiveReadinessDefaults"`
Expected: FAIL because the new accessors do not exist yet.

- [ ] **Step 3: Extend `JForexSessionConfig` minimally**

Add record fields and `fromEnvironment(false)` parsing for:

```java
boolean liveReadinessEnabled
int liveWarmupTicks
int liveLookbackDays
int liveBridgeWindowMinutes
int liveFreshnessSeconds
int liveStartupBridgeTimeoutMinutes
```

Use env names:

```text
BEHEMOTH_JFOREX_LIVE_READINESS_ENABLED=true
BEHEMOTH_JFOREX_LIVE_WARMUP_TICKS=30000
BEHEMOTH_JFOREX_LIVE_LOOKBACK_DAYS=31
BEHEMOTH_JFOREX_LIVE_BRIDGE_WINDOW_MINUTES=60
BEHEMOTH_JFOREX_LIVE_FRESHNESS_SECONDS=30
BEHEMOTH_JFOREX_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES=20
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.LiveReadinessCoordinatorTest.sessionConfigExposesLiveReadinessDefaults"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java
git commit -m "feat: add jforex live readiness config defaults"
```

## Task 2: Build Readiness State And Status Writer

**Files:**
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessState.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessSnapshot.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessSnapshot.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessRegistry.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessStatusWriter.java`
- Create: `src/jforex/src/test/java/com/behemoth/jforex/live/SymbolReadinessRegistryTest.java`
- Create: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessStatusWriterTest.java`

- [ ] **Step 1: Write the failing registry transition test**

```java
@Test
void registryTransitionsReadyToStaleAndBack() {
    SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));
    Instant now = Instant.parse("2026-03-22T12:00:00Z");

    registry.markReady("EURUSD", now, 312, now.minusSeconds(5));
    registry.refreshFreshness(now.plusSeconds(40), 30);
    assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);

    registry.recordFreshTick("EURUSD", now.plusSeconds(41));
    registry.refreshFreshness(now.plusSeconds(42), 30);
    assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
}
```

- [ ] **Step 2: Write the failing status-writer test**

```java
@Test
void statusWriterPersistsSchemaVersionedSnapshotAtomically() throws Exception {
    Path out = tempDir.resolve("data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json");
    LiveReadinessStatusWriter writer = new LiveReadinessStatusWriter(out, new ObjectMapper());
    writer.write(snapshot);
    JsonNode json = new ObjectMapper().readTree(Files.readString(out));
    assertThat(json.get("schema_version").asInt()).isEqualTo(1);
    assertThat(json.get("symbols").get(0).get("bridge_end_ts_utc").asText()).isNotBlank();
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.SymbolReadinessRegistryTest" --tests "com.behemoth.jforex.live.LiveReadinessStatusWriterTest"`
Expected: FAIL because the new files do not exist.

- [ ] **Step 4: Implement the immutable snapshots, registry, and atomic JSON writer**

Include:

```java
Files.writeString(tmp, json, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
```

Ensure the writer emits:

```json
{"schema_version":1,"as_of_utc":"...","run_id":"jforex_live","session_tradable_symbol_count":0,"session_total_symbol_count":6,"symbols":[...]}
```

Pin the output path exactly:

```java
Path readinessPath = sessionConfig.reportDir()
    .resolve("runtime")
    .resolve("live_symbol_readiness.json");
```

In live mode this must resolve to:

```text
data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.SymbolReadinessRegistryTest" --tests "com.behemoth.jforex.live.LiveReadinessStatusWriterTest"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessState.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessSnapshot.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessSnapshot.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/SymbolReadinessRegistry.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessStatusWriter.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/SymbolReadinessRegistryTest.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessStatusWriterTest.java
git commit -m "feat: add live symbol readiness registry"
```

## Task 3: Implement Historical Parquet Warmup Loader

**Files:**
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java`
- Create: `src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java`
- Check: `src/jforex/src/main/java/com/behemoth/jforex/local/ParquetTickLoader.java`

- [ ] **Step 1: Write the failing phase-preservation test**

```java
@Test
void loaderKeepsWarmupTicksPlusPhaseRemainder() throws Exception {
    HistoricalWarmupLoader loader = new HistoricalWarmupLoader();
    WarmupSlice slice = loader.load(config, "EURUSD", bridgeAnchorTs);
    assertThat(slice.ticks()).hasSize(30_075);
    assertThat(slice.bridgeAnchorTs()).isEqualTo(bridgeAnchorTs);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.HistoricalWarmupLoaderTest"`
Expected: FAIL because the loader does not exist.

- [ ] **Step 3: Implement `HistoricalWarmupLoader` by reusing the local harness rule**

Core logic:

```java
int preCount = countTicks(connection, parquetExpr, anchor.minus(lookbackDays, ChronoUnit.DAYS), anchor);
int keep = warmupTicks + (preCount % phaseBarTicks);
List<RuntimeTick> ticks = loadDescending(..., keep);
ticks.sort(Comparator.comparing(RuntimeTick::timestamp));
```

Return a small immutable result object such as:

```java
public record WarmupSlice(Instant bridgeAnchorTs, List<RuntimeTick> ticks) {}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.HistoricalWarmupLoaderTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java
git commit -m "feat: add live parquet warmup loader"
```

## Task 4: Implement Broker Bridge Loader With Sequence Continuity

**Files:**
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerHistoryPort.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/JForexBrokerHistoryPort.java`
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java`
- Create: `src/jforex/src/test/java/com/behemoth/jforex/live/BrokerBridgeLoaderTest.java`
- Check: `src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/IncomingTickPayload.java`
- Check: `src/behemoth/api/server.py`

- [ ] **Step 1: Write the failing bridge timeout test**

```java
@Test
void bridgeLoaderTimesOutWhenFreshnessNeverRecovers() {
    BrokerBridgeLoader loader = new BrokerBridgeLoader(fakeHistory, fakePredictionClient, registry, clock);
    loader.bridge(symbolConfig);
    assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
    assertThat(registry.snapshot("EURUSD").startupTimeoutReached()).isTrue();
}
```

- [ ] **Step 2: Write the failing sequence continuity test**

```java
@Test
void bridgeTicksContinueClientTickSequenceAfterBackfill() {
    BrokerBridgeLoader loader = new BrokerBridgeLoader(...);
    loader.seedClientTickSeq("EURUSD", 30_075L);
    loader.bridge(symbolConfig);
    assertThat(postedPayloads).extracting(IncomingTickPayload::clientTickSeq)
        .containsExactly(30_076L, 30_077L, 30_078L);
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.BrokerBridgeLoaderTest"`
Expected: FAIL because the bridge classes do not exist.

- [ ] **Step 4: Implement the bridge port and loader**

Use these signatures:

```java
public interface BrokerHistoryPort {
    List<RuntimeTick> getTicks(String symbol, Instant fromInclusive, Instant toInclusive) throws Exception;
}
```

```java
public final class JForexBrokerHistoryPort implements BrokerHistoryPort {
    private final IHistory history;
}
```

Bridge behavior:

- fetch 60-minute windows with `history.getTicks(instrument, fromMillis, toMillis)`
- post each window immediately to Python via `PythonPredictionClient.tickBatch(...)` so bridge ticks use the same live ingest path and `client_tick_seq` monotonicity rules as subsequent `onTick()` traffic
- maintain one `long nextClientTickSeq` per symbol across backfill, bridge, and live ticks
- consult `/runtime/feed/status` after each window
- stop on warm + fresh, or mark `ERROR_PAUSED` after 20 minutes

Use this dependency shape:

```java
public BrokerBridgeLoader(
        BrokerHistoryPort historyPort,
        PythonPredictionClient predictionClient,
        SymbolReadinessRegistry registry,
        Clock clock
) { ... }
```

Submit each bridge window as:

```java
predictionClient.tickBatch(new TickBatchRequestPayload(symbol, ticks, runId));
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.BrokerBridgeLoaderTest"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/live/BrokerHistoryPort.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/JForexBrokerHistoryPort.java \
        src/jforex/src/main/java/com/behemoth/jforex/live/BrokerBridgeLoader.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/BrokerBridgeLoaderTest.java
git commit -m "feat: add jforex broker bridge loader"
```

## Task 5: Gate New Entries In `BehemothStrategyCore`

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`

- [ ] **Step 1: Write the failing paused-symbol test**

Add:

```java
@Test
void pausedSymbolStillIngestsTicksButDoesNotSubmitOrders() throws Exception {
    core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
    core.setEntriesAllowed("EURUSD", false);
    // enqueue predict response with selected_exec=true
    core.onTick(new RuntimeTick("EURUSD", ts, 1.1000, 1.1002));
    core.flushSymbol("EURUSD");
    assertThat(executionPort.submittedOrders).isEmpty();
}
```

- [ ] **Step 2: Write the failing recovery test**

```java
@Test
void symbolCanResumeSubmittingAfterReadinessRecovers() throws Exception {
    core.setEntriesAllowed("EURUSD", false);
    core.setEntriesAllowed("EURUSD", true);
    core.onTick(new RuntimeTick("EURUSD", ts, 1.1000, 1.1002));
    core.flushSymbol("EURUSD");
    assertThat(executionPort.submittedOrders).hasSize(2);
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.BehemothStrategyCoreTest.pausedSymbolStillIngestsTicksButDoesNotSubmitOrders" --tests "com.behemoth.jforex.BehemothStrategyCoreTest.symbolCanResumeSubmittingAfterReadinessRecovers"`
Expected: FAIL because the core has no per-symbol entries gate.

- [ ] **Step 4: Implement the minimal gate**

Add to `SymbolRuntimeState`:

```java
boolean entriesAllowed = true;
```

Add to `BehemothStrategyCore`:

```java
public void setEntriesAllowed(String symbol, boolean allowed) { ... }
```

Guard submission only:

```java
if (!state.entriesAllowed) {
    continue;
}
```

Do not block tick ingestion, predict calls, lifecycle updates, account snapshots, or close handling.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.BehemothStrategyCoreTest.pausedSymbolStillIngestsTicksButDoesNotSubmitOrders" --tests "com.behemoth.jforex.BehemothStrategyCoreTest.symbolCanResumeSubmittingAfterReadinessRecovers"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java \
        src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java
git commit -m "feat: gate new jforex entries by symbol readiness"
```

## Task 6: Add Coordinator Integration, Metrics, And Runtime Status Output

**Files:**
- Create: `src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java`
- Create: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/observability/JForexMetrics.java`

- [ ] **Step 1: Write the failing mixed-session test**

```java
@Test
void coordinatorAllowsMixedReadyAndErrorPausedSymbols() throws Exception {
    LiveReadinessCoordinator coordinator = buildCoordinator();
    coordinator.initialize(List.of("EURUSD", "GBPUSD"));
    assertThat(coordinator.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
    assertThat(coordinator.snapshot("GBPUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
    assertThat(coreEntriesAllowed("EURUSD")).isTrue();
    assertThat(coreEntriesAllowed("GBPUSD")).isFalse();
}
```

- [ ] **Step 2: Write the failing stale-pause test**

```java
@Test
void staleFeedPausesNewEntriesOnly() throws Exception {
    coordinator.recordLiveTick("EURUSD", now);
    coordinator.onHeartbeat(now.plusSeconds(31));
    assertThat(coordinator.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);
    assertThat(coreEntriesAllowed("EURUSD")).isFalse();
}
```

- [ ] **Step 2b: Write the failing fixed-cadence snapshot test**

```java
@Test
void coordinatorRewritesStatusSnapshotEveryFiveSecondsWithoutTicks() throws Exception {
    LiveReadinessCoordinator coordinator = buildCoordinatorWithFakeClock();
    coordinator.initialize(context, core, List.of("EURUSD"));
    coordinator.onHeartbeat(start.plusSeconds(5));
    coordinator.onHeartbeat(start.plusSeconds(10));
    assertThat(statusWriter.writeCount()).isGreaterThanOrEqualTo(2);
}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.LiveReadinessCoordinatorTest"`
Expected: FAIL because the coordinator does not exist.

- [ ] **Step 4: Implement the coordinator and metrics hooks**

Coordinator responsibilities:

```java
void initialize(IContext context, BehemothStrategyCore core, List<String> symbols)
void recordLiveTick(String symbol, Instant tickTs)
void onHeartbeat(Instant now)
void close()
```

Snapshot cadence requirement:

- track `lastStatusWriteAt`
- rewrite the readiness snapshot on every state transition
- also rewrite whenever `now >= lastStatusWriteAt + 5 seconds`, even if no new ticks arrived
- drive this through `onHeartbeat(...)`, which must be called from both market callbacks and a small scheduled heartbeat while the strategy is running
- the scheduler may be a single-threaded `ScheduledExecutorService` started in `initialize(...)` and stopped in `close()`
- when `sessionConfig.liveReadinessEnabled()` is `false`, the coordinator must bypass warmup/bridge logic entirely, mark all configured symbols as entries-allowed immediately, and skip scheduler startup

Add Prometheus signals:

```java
Gauge readinessState
Gauge entriesAllowed
Gauge tickStalenessSeconds
Counter readinessTransitions
Counter readinessTimeouts
```

Wire `BehemothJForexStrategy`:

- create coordinator after `core.start(...)`
- run parquet warmup + broker bridge during `onStart`
- call `coordinator.recordLiveTick(...)` during `onTick`
- call `coordinator.onHeartbeat(...)` from `onTick` and `onBar`
- call `coordinator.close()` during `onStop`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.LiveReadinessCoordinatorTest"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java \
        src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java \
        src/jforex/src/main/java/com/behemoth/jforex/observability/JForexMetrics.java
git commit -m "feat: integrate live symbol readiness into jforex strategy"
```

## Task 7: End-To-End Verification And Docs Touch-Up

**Files:**
- Modify: `docs/strategy_bible/model_handoff.md`
- Modify: `docs/strategy_bible/operator_runbook.md`
- Check: `scripts/run_jforex_live.py`

- [ ] **Step 1: Add the failing docs expectation test if one exists; otherwise add a small targeted assertion to an existing docs contract test only if it already covers these files**

If no suitable docs contract test exists, skip new automated docs test and document the manual verification instead.

- [ ] **Step 2: Update the operator-facing docs**

Add concise text covering:

- local parquet + broker bridge startup
- `READY` / `STALE_PAUSED` / `ERROR_PAUSED`
- `30s` freshness SLA
- runtime file: `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json`

- [ ] **Step 3: Run focused Java tests**

Run:

```bash
gradle :jforex-adapter:test --tests "com.behemoth.jforex.live.*" --tests "com.behemoth.jforex.BehemothStrategyCoreTest"
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: Run the broader repo checks relevant to this change**

Run:

```bash
uv run pytest -q tests/test_api_server.py
gradle :jforex-adapter:test
uv run mkdocs build
```

Expected:

- `tests/test_api_server.py`: PASS
- `:jforex-adapter:test`: PASS
- `mkdocs build`: succeeds

- [ ] **Step 5: Manual live-paper verification on Dukascopy demo**

Run:

```bash
make jforex-live
```

Verify:

- at least one symbol reaches `READY`
- a deliberately starved symbol remains `ERROR_PAUSED` or `STALE_PAUSED` without killing the session
- `runtime/live_symbol_readiness.json` updates every few seconds
- no new entries are submitted for stale symbols
- fresh symbols continue to ingest and trade normally

- [ ] **Step 6: Commit**

```bash
git add docs/strategy_bible/model_handoff.md \
        docs/strategy_bible/operator_runbook.md
git commit -m "docs: document jforex live readiness states"
```

## Final Verification Checklist

- [ ] `gradle :jforex-adapter:test`
- [ ] `uv run pytest -q tests/test_api_server.py`
- [ ] `uv run mkdocs build`
- [ ] `make jforex-live` manual demo verification completed or explicitly deferred
- [ ] `git status --short` reviewed before handoff
