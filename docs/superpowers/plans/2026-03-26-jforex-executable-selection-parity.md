# JForex Executable Selection Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JForex historical parity report and submit only the executable post-gating prediction set, so `predict_cycle.selected_count` matches Python executable-selection semantics.

**Architecture:** Keep the change centered on the JForex core. `BehemothStrategyCore` will compute one authoritative executable-candidate set and one blocked-diagnostic summary, `Stage14ArtifactWriter` will emit the executable count plus compact blocked-reason diagnostics, and the Python reconciliation test will prove the richer `predict_cycle.detail` string still parses the executable `selected_count` correctly.

**Tech Stack:** Java 21, JUnit 5, Python 3.12, pytest, Gradle

---

### Task 1: Lock The Executable-Selection Contract In Tests

**Files:**
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`
- Modify: `tests/test_reconcile_jforex_outcomes.py`

- [ ] **Step 1: Add a failing core test for runtime-gated predictions**

In `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`, add this test directly after `pausedSymbolStillIngestsTicksButDoesNotSubmitOrders()` so it uses the same fixture style and proves `selected_count` must drop to zero when readiness gating blocks all otherwise-selected predictions:

```java
    @Test
    void predictCycleReportsZeroExecutableSelectionsWhenEntriesArePaused() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            [{
                              "symbol":"EURUSD",
                              "close_ts":"2025-07-07T00:00:00Z",
                              "candidate_uid":"oco|EURUSD|100|h6|cand_entries_paused_contract",
                              "pred_prob":0.78,
                              "threshold_exec":0.61,
                              "selected_exec":1,
                              "bar_ticks":100,
                              "horizon":6,
                              "barrier_pips":2.0,
                              "cap_pips":1.2,
                              "risk_blocked":false,
                              "risk_reservation_id":"rid-1"
                            }]
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-entries-paused-contract-test");
            Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
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
            RecordingExecutionPort port = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore, writer, JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.setEntriesAllowed("EURUSD", false);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            writer.writeReports(List.of("EURUSD"), List.of());

            assertThat(port.submittedOrders).isEmpty();
            String events = Files.readString(tempDir.resolve("EURUSD_test_runtime_events.csv"));
            assertThat(events).contains("prediction_count=1");
            assertThat(events).contains("selected_count=0");
            assertThat(events).contains("blocked_count=1");
            assertThat(events).contains("blocked_reasons=entries_paused");
        }
    }
```

- [ ] **Step 2: Add a failing writer test for richer predict-cycle diagnostics**

In `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`, add this new test after `recordPredictCycle_writesReplayCloseTimestamp()` so the reporting contract is explicit before implementation:

```java
    @Test
    void recordPredictCycle_writesExecutableAndBlockedDiagnostics() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "local_jforex");
        writer.recordPredictCycle(
                "EURUSD",
                Instant.parse("2026-02-07T12:00:00Z"),
                3,
                1,
                2,
                List.of("entries_paused", "active_candidate_lifecycle"),
                List.of(100)
        );
        writer.writeReports(List.of("EURUSD"), List.of());

        String content = Files.readString(tempDir.resolve("EURUSD_local_jforex_runtime_events.csv"));
        assertThat(content).contains("prediction_count=3");
        assertThat(content).contains("selected_count=1");
        assertThat(content).contains("blocked_count=2");
        assertThat(content).contains("blocked_reasons=entries_paused,active_candidate_lifecycle");
        assertThat(content).contains("close_ts=2026-02-07T12:00:00Z");
    }
```

- [ ] **Step 3: Add a failing Python regression for richer `predict_cycle.detail`**

In `tests/test_reconcile_jforex_outcomes.py`, extend the existing parser coverage by adding this test after `test_parse_predict_cycle_close_ts()`:

```python
def test_load_runtime_events_ignores_extra_predict_cycle_diagnostics(tmp_path):
    from scripts.reconcile_jforex_outcomes import load_runtime_events

    _write_runtime_events(tmp_path, "EURUSD", "jforex", [
        {
            "event_ts_utc": "2026-03-22T10:00:00Z",
            "symbol": "EURUSD",
            "category": "signal",
            "event_name": "predict_cycle",
            "pass": "true",
            "detail": (
                "prediction_count=4;selected_count=1;blocked_count=3;"
                "blocked_reasons=entries_paused,active_candidate_lifecycle,risk_blocked;"
                "close_ts=2026-02-07T12:00:00Z;completed_bar_ticks=[100]"
            ),
        },
    ])

    events = load_runtime_events(tmp_path, "EURUSD")
    assert events["predict_cycles"] == 1
    assert events["selected_count_total"] == 1
```

- [ ] **Step 4: Run the targeted tests to confirm they fail before production changes**

Run:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.Stage14ArtifactWriterTest
```

Expected:
- `tests/test_reconcile_jforex_outcomes.py` fails or passes depending on the parser already ignoring extra fields; if it passes, keep it as a guardrail.
- The Gradle run must fail because `recordPredictCycle(...)` does not yet accept blocked reasons and `BehemothStrategyCore` still emits `selected_count=1` for entries-paused predictions.

- [ ] **Step 5: Commit the red-test state**

Run:

```bash
git add tests/test_reconcile_jforex_outcomes.py \
  src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java \
  src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java
git commit -m "test: define executable selection parity contract"
```

Expected: one test-only commit that captures the intended contract.

### Task 2: Move JForex Selection Accounting To The Executable Boundary

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`

- [ ] **Step 1: Add a small internal summary record for executable selection accounting**

Near the bottom of `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`, before the execution-port test doubles, add this private record and helper so the runtime gate is explicit and reusable:

```java
    private record ExecutableSelectionSummary(
            List<PredictionResponseItem> executablePredictions,
            int blockedCount,
            List<String> blockedReasons
    ) {
    }

    private ExecutableSelectionSummary classifyExecutablePredictions(
            SymbolRuntimeState state,
            List<PredictionResponseItem> predictions
    ) {
        List<PredictionResponseItem> executable = new ArrayList<>();
        List<String> blockedReasons = new ArrayList<>();
        int blockedCount = 0;
        for (PredictionResponseItem prediction : predictions) {
            if (!prediction.isSelected()) {
                continue;
            }
            if (!prediction.isExecutable(sessionConfig.riskEnabled())) {
                blockedCount++;
                blockedReasons.add("risk_blocked");
                continue;
            }
            if (stateStore.hasActiveCandidateLifecycle(state.instrument.symbol(), prediction.candidateUid())) {
                blockedCount++;
                blockedReasons.add("active_candidate_lifecycle");
                continue;
            }
            if (state.lastTick == null) {
                blockedCount++;
                blockedReasons.add("missing_last_tick");
                continue;
            }
            if (!state.entriesAllowed) {
                blockedCount++;
                blockedReasons.add("entries_paused");
                continue;
            }
            executable.add(prediction);
        }
        return new ExecutableSelectionSummary(executable, blockedCount, blockedReasons);
    }
```

- [ ] **Step 2: Replace pre-gate `selected` accounting with the executable summary**

In the prediction block inside `flushSymbol(...)`, replace the current `selected` / `blocked` counting and the direct `for (PredictionResponseItem prediction : predictions)` submission loop with this shape:

```java
            ExecutableSelectionSummary selectionSummary =
                    classifyExecutablePredictions(state, predictions);
            int executableSelected = selectionSummary.executablePredictions().size();
            int blocked = selectionSummary.blockedCount();
            Instant predictCloseTs = predictions.stream()
                    .map(PredictionResponseItem::closeTs)
                    .filter(Objects::nonNull)
                    .findFirst()
                    .orElseGet(() -> state.lastTick != null ? state.lastTick.timestamp() : Instant.now());
            metrics.recordSelectedPredictions(state.instrument.symbol(), executableSelected, blocked);
            artifactWriter.recordPredictCycle(
                    state.instrument.symbol(),
                    predictCloseTs,
                    predictions.size(),
                    executableSelected,
                    blocked,
                    selectionSummary.blockedReasons(),
                    completedBarTicks
            );
            for (PredictionResponseItem prediction : selectionSummary.executablePredictions()) {
                submitOcoPlan(state, prediction.toDecision(sessionConfig.requestedVolumeUnits()));
            }
```

Delete the old per-prediction `continue` gate chain so there is only one authoritative executable set.

- [ ] **Step 3: Extend `Stage14ArtifactWriter.recordPredictCycle(...)` for blocked reasons**

In `src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java`, update the method signature and detail string to match the new tests:

```java
    public synchronized void recordPredictCycle(
            String symbol,
            Instant closeTs,
            int predictionCount,
            int selectedCount,
            int blockedCount,
            List<String> blockedReasons,
            List<Integer> completedBarTicks
    ) {
        Instant replayCloseTs = Objects.requireNonNull(closeTs, "closeTs");
        String blockedReasonDetail = blockedReasons == null || blockedReasons.isEmpty()
                ? ""
                : ";blocked_reasons=" + String.join(",", blockedReasons);
        events.add(EventRow.pass(
                symbol,
                "signal",
                "predict_cycle",
                "prediction_count=" + predictionCount
                        + ";selected_count=" + selectedCount
                        + ";blocked_count=" + blockedCount
                        + blockedReasonDetail
                        + ";close_ts=" + replayCloseTs
                        + ";completed_bar_ticks=" + completedBarTicks
        ));
    }
```

Then update every call site in `Stage14ArtifactWriterTest.java` to pass `List.of()` for blocked reasons unless the test is intentionally exercising them.

- [ ] **Step 4: Run the targeted tests to verify the contract now passes**

Run:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.Stage14ArtifactWriterTest
```

Expected:
- `tests/test_reconcile_jforex_outcomes.py` passes
- the focused Gradle suite passes

- [ ] **Step 5: Commit the executable-boundary refactor**

Run:

```bash
git add src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java \
  src/jforex/src/main/java/com/behemoth/jforex/reporting/Stage14ArtifactWriter.java \
  src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java \
  src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java \
  tests/test_reconcile_jforex_outcomes.py
git commit -m "fix: align jforex selected count to executable candidates"
```

Expected: one implementation commit covering the core/reporting/test updates.

### Task 3: Prove The New Contract Against The Monthly Recert Path

**Files:**
- Modify: `tests/test_reconcile_jforex_outcomes.py`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java`

- [ ] **Step 1: Add a narrow Java regression for active-candidate lifecycle blocking**

In `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`, add a second runtime-gating test after the entries-paused contract test so executable selection also stays honest when a lifecycle already exists:

```java
    @Test
    void predictCycleReportsBlockedCandidatesWhenLifecycleAlreadyExists() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            [{
                              "symbol":"EURUSD",
                              "close_ts":"2025-07-07T00:01:00Z",
                              "candidate_uid":"oco|EURUSD|100|h6|cand_existing_lifecycle",
                              "pred_prob":0.78,
                              "threshold_exec":0.61,
                              "selected_exec":1,
                              "bar_ticks":100,
                              "horizon":6,
                              "barrier_pips":2.0,
                              "cap_pips":1.2,
                              "risk_blocked":false,
                              "risk_reservation_id":"rid-1"
                            }]
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-active-lifecycle-contract-test");
            Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
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
            RecordingExecutionPort port = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore, writer, JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            stateStore.registerPlannedGroup(
                    "EURUSD",
                    new PredictionDecision(
                            "EURUSD",
                            "oco|EURUSD|100|h6|cand_existing_lifecycle",
                            2.0,
                            1.2,
                            100,
                            6,
                            10_000.0,
                            "rid-existing"
                    ),
                    OcoOrderPlanner.build(
                            new PredictionDecision(
                                    "EURUSD",
                                    "oco|EURUSD|100|h6|cand_existing_lifecycle",
                                    2.0,
                                    1.2,
                                    100,
                                    6,
                                    10_000.0,
                                    "rid-existing"
                            ),
                            1.1000,
                            1.1002,
                            0.0001,
                            Instant.parse("2025-07-07T00:00:00Z")
                    ),
                    "run-1",
                    Instant.parse("2025-07-07T00:00:00Z"),
                    false
            );
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:01:00Z"), 1.1000, 1.1002));
            writer.writeReports(List.of("EURUSD"), List.of());

            assertThat(port.submittedOrders).isEmpty();
            String events = Files.readString(tempDir.resolve("EURUSD_test_runtime_events.csv"));
            assertThat(events).contains("selected_count=0");
            assertThat(events).contains("blocked_count=1");
            assertThat(events).contains("blocked_reasons=active_candidate_lifecycle");
        }
    }
```

- [ ] **Step 2: Re-run the focused verification plus one real recert smoke**

Run:

```bash
uv run pytest -q tests/test_reconcile_jforex_outcomes.py
gradle :jforex-adapter:test --tests com.behemoth.jforex.BehemothStrategyCoreTest --tests com.behemoth.jforex.Stage14ArtifactWriterTest
make monthly-recert MODEL_MONTH=2026-02
```

Expected:
- targeted Python and Java suites pass
- `make monthly-recert MODEL_MONTH=2026-02` no longer fails because `selected_count` was inflated ahead of runtime gating
- `USDCAD` still remains the explicit `NO_GO` `no_gate_states` case

- [ ] **Step 3: Commit the end-to-end parity verification follow-through**

Run:

```bash
git add src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java \
  src/jforex/src/test/java/com/behemoth/jforex/Stage14ArtifactWriterTest.java \
  tests/test_reconcile_jforex_outcomes.py
git commit -m "test: cover jforex runtime gating parity"
```

Expected: one final regression-test commit covering the lifecycle-blocking parity case and the post-refactor verification edits from Task 3.
