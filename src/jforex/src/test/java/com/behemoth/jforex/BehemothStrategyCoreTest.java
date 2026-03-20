package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.ExecutionPort;
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
}
