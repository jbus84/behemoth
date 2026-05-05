package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;

class QueueBatchingTest {

    private static SymbolWorker createWorker(MockWebServer server, String symbol, int tickBatchSize) throws Exception {
        Path tempDir = Files.createTempDirectory("batch-test");
        JForexSessionConfig sessionConfig = new JForexSessionConfig(
                server.url("/").uri(),
                URI.create("http://example.test/jnlp"),
                "user",
                "pass",
                "",
                List.of(symbol),
                Instant.parse("2025-01-01T00:00:00Z"),
                Instant.parse("2025-01-02T00:00:00Z"),
                tempDir,
                "run-test",
                false,
                10000.0,
                tickBatchSize,
                900L,
                false,
                1,
                false,
                "",
                0,
                false,
                false,
                0,
                0,
                0,
                0,
                0,
                1000
        );
        PythonPredictionClient client = new PythonPredictionClient(
                HttpClient.newHttpClient(),
                server.url("/").uri(),
                Duration.ofMillis(50),
                Duration.ofMillis(50)
        );
        JForexMetrics metrics = JForexMetrics.start(sessionConfig);
        Stage14ArtifactWriter artifactWriter = new Stage14ArtifactWriter(tempDir, "test");
        SymbolWorker.ActionCallbacks callbacks = new SymbolWorker.ActionCallbacks() {
            @Override public boolean entriesAllowed(String symbol) {
                return true;
            }
            @Override public void submitMarketOrder(String symbol, String label, String side, double amountMillions,
                                                     String scanId, String candidateUid, String reservationId, int horizon,
                                                     Instant now) {
            }
            @Override public void closePositionByScanId(String symbol, String scanId, Instant now) {
            }
        };
        return new SymbolWorker(symbol, sessionConfig, client, metrics, artifactWriter, callbacks);
    }

    private static Dispatcher tickBatchDispatcher() {
        return new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                return new MockResponse()
                        .setBody("""
                                {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                """)
                        .addHeader("Content-Type", "application/json");
            }
        };
    }

    @Test
    void largeEnqueueCreatesBatches() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.setDispatcher(tickBatchDispatcher());

            SymbolWorker worker = createWorker(server, "EURUSD", 100);
            worker.start();

            for (int i = 0; i < 500; i++) {
                worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
            }

            worker.drain();
            worker.stop();

            assertThat(server.getRequestCount()).isGreaterThanOrEqualTo(3);
        }
    }

    @Test
    void noTicksAreDropped() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.setDispatcher(tickBatchDispatcher());

            SymbolWorker worker = createWorker(server, "EURUSD", 100);
            worker.start();

            for (int i = 0; i < 500; i++) {
                worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
            }

            worker.drain();
            worker.stop();

            ObjectMapper mapper = new ObjectMapper()
                    .registerModule(new JavaTimeModule())
                    .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                    .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

            int totalTicks = 0;
            int requestCount = server.getRequestCount();
            for (int i = 0; i < requestCount; i++) {
                var req = server.takeRequest();
                if (req != null && req.getBody() != null) {
                    String body = req.getBody().readUtf8();
                    TickBatchRequestPayload payload = mapper.readValue(body, TickBatchRequestPayload.class);
                    totalTicks += payload.ticks().size();
                }
            }

            assertThat(totalTicks).isEqualTo(500);
        }
    }
}
