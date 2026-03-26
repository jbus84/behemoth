package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.ExecutionPort;
import com.behemoth.jforex.core.OrderEvent;
import com.behemoth.jforex.core.OrderEventType;
import com.behemoth.jforex.core.OrderHandle;
import com.behemoth.jforex.core.OrderRequest;
import com.behemoth.jforex.core.RuntimeInstrument;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.domain.PredictionDecision;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.state.ExecutionStateStore;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;

class BehemothStrategyCoreTest {
    @Test
    void flushSymbolRetriesTimedOutTickBatch() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"AUDUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .setHeadersDelay(250, java.util.concurrent.TimeUnit.MILLISECONDS)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"AUDUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-core-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(),
                    URI.create("http://example.test/jnlp"),
                    "user",
                    "pass",
                    "",
                    List.of("AUDUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"),
                    Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir,
                    "run-1",
                    false,
                    10_000.0,
                    1,
                    900L,
                    false,
                    1,
                    false,
                    "",
                    0
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(),
                    server.url("/").uri(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(50)
            );
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state").resolve("execution-state.json"),
                    client.objectMapper()
            );
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig,
                    client,
                    stateStore,
                    new Stage14ArtifactWriter(tempDir, "local_jforex"),
                    JForexMetrics.start(sessionConfig),
                    new NoopExecutionPort()
            );

            core.start(List.of(new RuntimeInstrument("AUDUSD", 0.0001)));

            assertThatCode(() -> core.onTick(new RuntimeTick(
                    "AUDUSD",
                    Instant.parse("2025-07-07T00:00:00Z"),
                    0.6550,
                    0.6552
            ))).doesNotThrowAnyException();

            assertThat(server.getRequestCount()).isEqualTo(3);
            assertThat(server.takeRequest(1, TimeUnit.SECONDS)).isNotNull();
            assertThat(server.takeRequest(1, TimeUnit.SECONDS)).isNotNull();
            assertThat(server.takeRequest(1, TimeUnit.SECONDS)).isNotNull();
        }
    }

    @Test
    void flushSymbolFallsBackToSingleTickAfterRepeatedBatchTimeouts() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            for (int i = 0; i < 3; i++) {
                server.enqueue(new MockResponse()
                        .setBody("""
                                {"ok":true,"symbol":"AUDUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                """)
                        .setHeadersDelay(250, java.util.concurrent.TimeUnit.MILLISECONDS)
                        .addHeader("Content-Type", "application/json"));
            }
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"AUDUSD","tick_accepted":true,"drop_reason":null,"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_completed":false,"completed_bar_ticks":[],"bar_count":1}
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-core-fallback-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(),
                    URI.create("http://example.test/jnlp"),
                    "user",
                    "pass",
                    "",
                    List.of("AUDUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"),
                    Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir,
                    "run-1",
                    false,
                    10_000.0,
                    1,
                    900L,
                    false,
                    1,
                    false,
                    "",
                    0
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(),
                    server.url("/").uri(),
                    Duration.ofMillis(50),
                    Duration.ofMillis(50)
            );
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state").resolve("execution-state.json"),
                    client.objectMapper()
            );
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig,
                    client,
                    stateStore,
                    new Stage14ArtifactWriter(tempDir, "local_jforex"),
                    JForexMetrics.start(sessionConfig),
                    new NoopExecutionPort()
            );

            core.start(List.of(new RuntimeInstrument("AUDUSD", 0.0001)));

            assertThatCode(() -> core.onTick(new RuntimeTick(
                    "AUDUSD",
                    Instant.parse("2025-07-07T00:00:00Z"),
                    0.6550,
                    0.6552
            ))).doesNotThrowAnyException();

            assertThat(server.getRequestCount()).isEqualTo(5);
        }
    }

    @Test
    void pausedSymbolStillIngestsTicksButDoesNotSubmitOrders() throws Exception {
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
                              "candidate_uid":"oco|EURUSD|100|h6|cand_entries_paused",
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

            Path tempDir = Files.createTempDirectory("behemoth-entries-paused-test");
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
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.setEntriesAllowed("EURUSD", false);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            core.flushSymbol("EURUSD");

            assertThat(port.submittedOrders).isEmpty();
            assertThat(server.getRequestCount()).isEqualTo(3);
        }
    }

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
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.setEntriesAllowed("EURUSD", false);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            core.stop();

            String runtimeEvents = Files.readString(tempDir.resolve("EURUSD_test_runtime_events.csv"));
            assertThat(port.submittedOrders).isEmpty();
            assertThat(runtimeEvents).contains("prediction_count=1");
            assertThat(runtimeEvents).contains("selected_count=0");
            assertThat(runtimeEvents).contains("blocked_count=1");
            assertThat(runtimeEvents).contains("blocked_reasons=entries_paused");
            assertThat(server.getRequestCount()).isEqualTo(3);
        }
    }

    @Test
    void predictCycleReportsActiveCandidateLifecycleBlocking() throws Exception {
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
                              "candidate_uid":"oco|EURUSD|100|h6|cand_active_lifecycle_contract",
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
                    "EURUSD", "oco|EURUSD|100|h6|cand_active_lifecycle_contract", 2.0, 1.2, 100, 6, 10_000.0, "rid-existing");
            Instant placedAt = Instant.parse("2025-07-06T23:59:00Z");
            OcoOrderPlan plan = OcoOrderPlanner.build(decision, 1.1000, 1.1002, 0.0001, placedAt);
            stateStore.registerPlannedGroup("EURUSD", decision, plan, "run-existing", placedAt, false);

            RecordingExecutionPort port = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            core.stop();

            String runtimeEvents = Files.readString(tempDir.resolve("EURUSD_test_runtime_events.csv"));
            assertThat(port.submittedOrders).isEmpty();
            assertThat(runtimeEvents).contains("prediction_count=1");
            assertThat(runtimeEvents).contains("selected_count=0");
            assertThat(runtimeEvents).contains("blocked_count=1");
            assertThat(runtimeEvents).contains("blocked_reasons=active_candidate_lifecycle");
            assertThat(server.getRequestCount()).isEqualTo(3);
        }
    }

    @Test
    void predictCyclePreservesSpecificRiskBlockReasonInDiagnostics() throws Exception {
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
                              "candidate_uid":"oco|EURUSD|100|h6|cand_risk_reason_contract",
                              "pred_prob":0.78,
                              "threshold_exec":0.61,
                              "selected_exec":1,
                              "bar_ticks":100,
                              "horizon":6,
                              "barrier_pips":2.0,
                              "cap_pips":1.2,
                              "risk_blocked":true,
                              "risk_block_reason":"risk_budget_exhausted",
                              "risk_reservation_id":"rid-1"
                            }]
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-risk-reason-contract-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(), URI.create("http://example.test/jnlp"),
                    "user", "pass", "", List.of("EURUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir, "run-1",
                    true, 10_000.0, 1, 900L, false, 60, false, "", 0
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri(),
                    Duration.ofSeconds(5), Duration.ofSeconds(5));
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state.json"), client.objectMapper());
            RecordingExecutionPort port = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            core.stop();

            String runtimeEvents = Files.readString(tempDir.resolve("EURUSD_test_runtime_events.csv"));
            assertThat(port.submittedOrders).isEmpty();
            assertThat(runtimeEvents).contains("selected_count=0");
            assertThat(runtimeEvents).contains("blocked_count=1");
            assertThat(runtimeEvents).contains("blocked_reasons=risk_budget_exhausted");
        }
    }

    @Test
    void symbolCanResumeSubmittingAfterReadinessRecovers() throws Exception {
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
                              "candidate_uid":"oco|EURUSD|100|h6|cand_entries_paused_cycle",
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
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":2,"last_tick_ts_utc":"2025-07-07T00:01:00Z","last_client_tick_seq":2,"bar_count":290}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            [{
                              "symbol":"EURUSD",
                              "close_ts":"2025-07-07T00:01:00Z",
                              "candidate_uid":"oco|EURUSD|100|h6|cand_entries_resumed_cycle",
                              "pred_prob":0.79,
                              "threshold_exec":0.61,
                              "selected_exec":1,
                              "bar_ticks":100,
                              "horizon":6,
                              "barrier_pips":2.0,
                              "cap_pips":1.2,
                              "risk_blocked":false,
                              "risk_reservation_id":"rid-2"
                            }]
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-entries-recover-test");
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
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.setEntriesAllowed("EURUSD", false);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            assertThat(port.submittedOrders).isEmpty();

            core.setEntriesAllowed("EURUSD", true);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:01:00Z"), 1.1001, 1.1003));
            assertThat(port.submittedOrders).hasSize(2);
        }
    }

    @Test
    void predictServiceUnavailableDoesNotCrashTickProcessing() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"live","record_raw_ticks":true,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setResponseCode(503)
                    .setBody("""
                            {"detail":"No model binding registered for EURUSD"}
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-predict-503-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(), URI.create("http://example.test/jnlp"),
                    "user", "pass", "", List.of("EURUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir, "run-1",
                    true, 10_000.0, 1, 900L, false, 60, false, "", 0
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri(),
                    Duration.ofSeconds(5), Duration.ofSeconds(5));
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state.json"), client.objectMapper());
            RecordingExecutionPort port = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), port);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

            assertThatCode(() -> core.onTick(new RuntimeTick(
                    "EURUSD",
                    Instant.parse("2025-07-07T00:00:00Z"),
                    1.1000,
                    1.1002
            ))).doesNotThrowAnyException();

            assertThat(port.submittedOrders).isEmpty();
            assertThat(server.getRequestCount()).isEqualTo(3);
        }
    }
    private static final class NoopExecutionPort implements ExecutionPort {
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
        }
    }

    private static final class RecordingExecutionPort implements ExecutionPort {
        final List<OrderRequest> submittedOrders = new ArrayList<>();
        final List<String> closePositionCalls = new ArrayList<>();

        @Override
        public OrderHandle submitStopOrder(OrderRequest request) {
            submittedOrders.add(request);
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
                    0.0, null, null, "fill", null));

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
                    0.0, null, null, "fill", null));

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
                    0.4, "broker_close", null));

            // Drive bars 3–5: closePosition must NOT be called (pending exit was removed)
            for (int i = 2; i < 5; i++) {
                core.onTick(new RuntimeTick("EURUSD",
                        Instant.parse("2025-07-07T00:0" + (i + 1) + ":00Z"), 1.0854, 1.0856));
            }
            assertThat(port.closePositionCalls).isEmpty();
        }
    }

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
                    0.0, null, null, "fill_a", null));
            core.onOrderEvent(new OrderEvent(
                    OrderEventType.FILL_OK, "EURUSD",
                    planB.buyLeg().label(), "broker-b-buy",
                    1.0863, Instant.parse("2025-07-07T00:00:02Z"),
                    0.0, null, null, "fill_b", null));

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
                    0.0, null, null, "warmup_fill", null));

            // Warmup bar 1 — no close yet (1 < horizon=2)
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:01:00Z"), 1.0854, 1.0856));
            assertThat(port.closePositionCalls).isEmpty();

            // Warmup bar 2 — horizon reached; closePosition triggered
            core.onTick(new RuntimeTick("EURUSD",
                    Instant.parse("2025-07-07T00:02:00Z"), 1.0854, 1.0856));
            assertThat(port.closePositionCalls).containsExactly(plan.buyLeg().label());
        }
    }
}
