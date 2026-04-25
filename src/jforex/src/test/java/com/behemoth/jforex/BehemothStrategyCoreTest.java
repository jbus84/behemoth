package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.OrderEvent;
import com.behemoth.jforex.core.OrderEventType;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.ExecutionPort;
import com.behemoth.jforex.core.MarketOrderRequest;
import com.behemoth.jforex.core.OrderHandle;
import com.behemoth.jforex.core.OrderRequest;
import com.behemoth.jforex.core.RuntimeInstrument;
import com.behemoth.jforex.core.RuntimeTick;
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

            assertThat(port.marketOrders).isEmpty();
            assertThat(server.getRequestCount()).isEqualTo(3);
        }
    }

    @Test
    void executesOpenMarketActionFromPredictResponse() throws Exception {
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
                            {
                              "predictions": [{
                                "symbol":"EURUSD",
                                "close_ts":"2025-07-07T00:00:00Z",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "pred_prob":0.78,
                                "threshold_exec":0.61,
                                "selected_exec":1,
                                "bar_ticks":100,
                                "horizon":6,
                                "barrier_pips":2.0,
                                "cap_pips":1.2,
                                "risk_blocked":false,
                                "risk_reservation_id":"rid-1"
                              }],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-001",
                                "side":"BUY",
                                "reservation_id":"rid-1",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-open-market-test");
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
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(port.marketOrders).hasSize(1);
            MarketOrderRequest order = port.marketOrders.get(0);
            assertThat(order.symbol()).isEqualTo("EURUSD");
            assertThat(order.side()).isEqualTo("BUY");
            assertThat(order.label()).isEqualTo("BM_scan-001_BUY");
        }
    }

    @Test
    void executeActionsSkipsMarketOrderWhenEntriesNotAllowed() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,
                            "bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,
                            "last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [{"candidate_uid":"oco|EURUSD|100|h6|cand1","is_selected":true,
                                "score":0.9,"threshold":0.5,"close_ts":"2025-07-07T01:00:00Z"}],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-blocked",
                                "side":"BUY",
                                "reservation_id":"res-blocked",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-entry-gate-test");
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
            RecordingExecutionPort recordingPort = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), recordingPort);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.setEntriesAllowed("EURUSD", false);
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(recordingPort.marketOrders).isEmpty();
        }
    }

    @Test
    void executeActionsSubmitsMarketOrderWhenEntriesAllowed() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,
                            "bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,
                            "last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [{"candidate_uid":"oco|EURUSD|100|h6|cand1","is_selected":true,
                                "score":0.9,"threshold":0.5,"close_ts":"2025-07-07T01:00:00Z"}],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-allowed",
                                "side":"BUY",
                                "reservation_id":"res-allowed",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-entry-gate-allowed-test");
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
            RecordingExecutionPort recordingPort = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), recordingPort);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(recordingPort.marketOrders).hasSize(1);
            assertThat(recordingPort.marketOrders.get(0).label()).isEqualTo("BM_scan-allowed_BUY");
        }
    }

    @Test
    void fillEventSyncToOpenTradeUsesHorizonAndCandidateUidFromAction() throws Exception {
        // When a fill arrives after an OPEN_MARKET action, /trades/open must receive
        // the candidateUid, reservationId, and horizon from the action — not hardcoded zeros.
        try (MockWebServer server = new MockWebServer()) {
            // feedStatus
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"live","record_raw_ticks":true,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            // tick batch (bar completed -> triggers predict)
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            // predict response with OPEN_MARKET action carrying horizon=6
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-42",
                                "side":"BUY",
                                "reservation_id":"res-xyz",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));
            // /trades/open response
            server.enqueue(new MockResponse()
                    .setBody("{\"status\":\"ok\",\"internal_trade_id\":\"t-1\"}")
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-fill-horizon-test");
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
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), new NoopExecutionPort());

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            // Trigger tick -> predict -> OPEN_MARKET action cached internally
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            // Simulate broker fill on the label produced by executeActions
            core.onOrderEvent(new OrderEvent(
                    OrderEventType.FILL_OK,
                    "EURUSD",
                    "BM_scan-42_BUY",
                    "broker-pos-999",
                    1.1001,
                    Instant.parse("2025-07-07T00:00:01Z"),
                    0.0,
                    null,
                    null,
                    null,
                    null
            ));

            // Drain setup requests (feedStatus, tickBatch, predict)
            server.takeRequest(1, TimeUnit.SECONDS);
            server.takeRequest(1, TimeUnit.SECONDS);
            server.takeRequest(1, TimeUnit.SECONDS);

            // The 4th request must be POST /trades/open with correct fields
            var tradeOpenReq = server.takeRequest(1, TimeUnit.SECONDS);
            assertThat(tradeOpenReq).isNotNull();
            assertThat(tradeOpenReq.getPath()).isEqualTo("/trades/open");

            String body = tradeOpenReq.getBody().readUtf8();
            assertThat(body).contains("\"candidate_uid\":\"oco|EURUSD|100|h6|cand1\"");
            assertThat(body).contains("\"reservation_id\":\"res-xyz\"");
            assertThat(body).contains("\"horizon\":6");
        }
    }

    @Test
    void closeMarketUsesOrderLabelFromOpenMarketNotBrokerPosId() throws Exception {
        // Regression test: closePosition must use the JForex order label (e.g. "BM_scan-001_BUY"),
        // NOT the numeric broker_pos_id from Python. The JForex engine.getOrder() API only accepts
        // labels, so passing a numeric ID silently returns null and the close is never submitted.
        try (MockWebServer server = new MockWebServer()) {
            // 1. session config
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"historical_auto","record_raw_ticks":false,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            // 2. first bar completes → OPEN_MARKET for scan-001
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-001",
                                "side":"BUY",
                                "reservation_id":"rid-1",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));
            // 3. second bar completes → CLOSE_MARKET for scan-001 (broker_pos_id is numeric)
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":2,"last_tick_ts_utc":"2025-07-07T00:01:00Z","last_client_tick_seq":2,"bar_count":290}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [],
                              "actions": [{
                                "type":"CLOSE_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-001",
                                "broker_pos_id":"272947788"
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-close-market-label-test");
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
            // bar 1: OPEN_MARKET
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));
            // bar 2: CLOSE_MARKET
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:01:00Z"), 1.1010, 1.1012));

            // Must use the JForex order label, NOT the numeric broker_pos_id "272947788"
            assertThat(port.closePositionCalls).containsExactly("BM_scan-001_BUY");
        }
    }

    @Test
    void emptyActionsDoesNotSubmitAnyOrders() throws Exception {
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
                            {
                              "predictions": [{
                                "symbol":"EURUSD",
                                "close_ts":"2025-07-07T00:00:00Z",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "pred_prob":0.78,
                                "threshold_exec":0.61,
                                "selected_exec":1,
                                "bar_ticks":100,
                                "horizon":6,
                                "barrier_pips":2.0,
                                "cap_pips":1.2,
                                "risk_blocked":false,
                                "risk_reservation_id":"rid-1"
                              }],
                              "actions": []
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-empty-actions-test");
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
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(port.marketOrders).isEmpty();
            assertThat(port.closePositionCalls).isEmpty();
        }
    }

    private static final class NoopExecutionPort implements ExecutionPort {
        @Override
        public OrderHandle submitStopOrder(OrderRequest request) {
            return new OrderHandle(request.label(), request.label());
        }

        @Override
        public OrderHandle submitMarketOrder(MarketOrderRequest request) {
            return new OrderHandle(request.label(), request.label());
        }

        @Override
        public void cancelOrder(String symbol, String label) {
        }

        @Override
        public void closePosition(String symbol, String label) {
        }
    }

    @Test
    void executeActionsSkipsMarketOrderWhenNewEntriesGloballyDisabled() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"as_of_utc":"2025-07-07T00:00:00Z","governance_mode":"live","record_raw_ticks":true,"symbols":[]}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,
                            "bar_completed":true,"completed_bar_ticks":[100],"symbol_tick_seq":1,
                            "last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":289}
                            """)
                    .addHeader("Content-Type", "application/json"));
            server.enqueue(new MockResponse()
                    .setBody("""
                            {
                              "predictions": [],
                              "actions": [{
                                "type":"OPEN_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-drain-only",
                                "side":"BUY",
                                "reservation_id":"res-drain-only",
                                "broker_pos_id":null,
                                "horizon":6
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-new-entries-disabled-test");
            JForexSessionConfig sessionConfig = new JForexSessionConfig(
                    server.url("/").uri(), URI.create("http://example.test/jnlp"),
                    "user", "pass", "", List.of("EURUSD"),
                    Instant.parse("2025-07-07T00:00:00Z"), Instant.parse("2025-07-09T00:00:00Z"),
                    tempDir, "run-1",
                    false, 10_000.0, 1, 900L, false, 60, false, "", 0,
                    false
            );
            PythonPredictionClient client = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri(),
                    Duration.ofSeconds(5), Duration.ofSeconds(5));
            ExecutionStateStore stateStore = new ExecutionStateStore(
                    tempDir.resolve("state.json"), client.objectMapper());
            RecordingExecutionPort recordingPort = new RecordingExecutionPort();
            BehemothStrategyCore core = new BehemothStrategyCore(
                    sessionConfig, client, stateStore,
                    new Stage14ArtifactWriter(tempDir, "test"),
                    JForexMetrics.start(sessionConfig), recordingPort);

            core.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));
            core.onTick(new RuntimeTick("EURUSD", Instant.parse("2025-07-07T00:00:00Z"), 1.1000, 1.1002));

            assertThat(recordingPort.marketOrders).isEmpty();
        }
    }

    private static final class RecordingExecutionPort implements ExecutionPort {
        final List<OrderRequest> submittedOrders = new ArrayList<>();
        final List<MarketOrderRequest> marketOrders = new ArrayList<>();
        final List<String> closePositionCalls = new ArrayList<>();

        @Override
        public OrderHandle submitStopOrder(OrderRequest request) {
            submittedOrders.add(request);
            return new OrderHandle(request.label(), request.label());
        }

        @Override
        public OrderHandle submitMarketOrder(MarketOrderRequest request) {
            marketOrders.add(request);
            return new OrderHandle(request.label(), request.label());
        }

        @Override
        public void cancelOrder(String symbol, String label) {
        }

        @Override
        public void closePosition(String symbol, String label) {
            closePositionCalls.add(label);
        }
    }
}
