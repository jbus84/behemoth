package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.behemoth.jforex.config.JForexSessionConfig;
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
                                "broker_pos_id":null
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
    void executesCloseMarketActionFromPredictResponse() throws Exception {
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
                              "predictions": [],
                              "actions": [{
                                "type":"CLOSE_MARKET",
                                "symbol":"EURUSD",
                                "candidate_uid":"oco|EURUSD|100|h6|cand1",
                                "scan_id":"scan-001",
                                "side":"BUY",
                                "reservation_id":"rid-1",
                                "broker_pos_id":"broker-pos-123"
                              }]
                            }
                            """)
                    .addHeader("Content-Type", "application/json"));

            Path tempDir = Files.createTempDirectory("behemoth-close-market-test");
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

            assertThat(port.closePositionCalls).containsExactly("broker-pos-123");
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
}
