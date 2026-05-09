package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.OrderIntent;
import com.behemoth.jforex.core.OrderResult;
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
import java.util.concurrent.atomic.AtomicInteger;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;

class SymbolWorkerFailureTest {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static SymbolWorker createWorker(MockWebServer server, String symbol, int tickBatchSize) throws Exception {
        Path tempDir = Files.createTempDirectory("worker-failure-test");
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
        SymbolWorker.SymbolStateReader stateReader = sym -> true;
        SymbolWorker.OrderBookingPort bookingPort = new SymbolWorker.OrderBookingPort() {
            @Override public OrderResult submitMarketOrder(OrderIntent intent) {
                return new OrderResult("", "", intent.reservationId());
            }
            @Override public void closePositionByScanId(String symbol, String scanId, Instant now) {
            }
        };
        return new SymbolWorker(symbol, sessionConfig, client, metrics, artifactWriter, stateReader, bookingPort);
    }

    @Test
    void workerSurvivesProcessorException() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            AtomicInteger requestCount = new AtomicInteger(0);
            AtomicInteger total = new AtomicInteger(0);
            server.setDispatcher(new Dispatcher() {
                @Override public MockResponse dispatch(RecordedRequest request) {
                    int req = requestCount.incrementAndGet();
                    try {
                        String body = request.getBody().readUtf8();
                        TickBatchRequestPayload payload = MAPPER.readValue(body, TickBatchRequestPayload.class);
                        int count = payload.ticks().size();
                        if (req == 1) {
                            return new MockResponse()
                                    .setResponseCode(500)
                                    .setBody("{\"detail\":\"simulated failure\"}")
                                    .addHeader("Content-Type", "application/json");
                        }
                        total.addAndGet(count);
                        return new MockResponse()
                                .setBody("""
                                    {"ok":true,"symbol":"EURUSD","ticks_received":%d,"accepted_count":%d,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                    """.formatted(count, count))
                                .addHeader("Content-Type", "application/json");
                    } catch (Exception e) {
                        return new MockResponse().setResponseCode(500).setBody(e.getMessage());
                    }
                }
            });

            SymbolWorker worker = createWorker(server, "EURUSD", 1);
            worker.start();

            worker.enqueue(new RuntimeTick("EURUSD", Instant.parse("2025-01-01T00:00:00Z"), 1.1000, 1.1002));
            Thread.sleep(50L);
            worker.enqueue(new RuntimeTick("EURUSD", Instant.parse("2025-01-01T00:00:01Z"), 1.1001, 1.1003));

            worker.drain();
            worker.stop();

            assertThat(requestCount.get()).isGreaterThanOrEqualTo(2);
            assertThat(total.get()).isGreaterThanOrEqualTo(1);
        }
    }

    @Test
    void workerSurvivesInterruptedExceptionDuringTake() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            AtomicInteger total = new AtomicInteger(0);
            server.setDispatcher(new Dispatcher() {
                @Override public MockResponse dispatch(RecordedRequest request) {
                    try {
                        String body = request.getBody().readUtf8();
                        TickBatchRequestPayload payload = MAPPER.readValue(body, TickBatchRequestPayload.class);
                        int count = payload.ticks().size();
                        total.addAndGet(count);
                        return new MockResponse()
                                .setBody("""
                                    {"ok":true,"symbol":"EURUSD","ticks_received":%d,"accepted_count":%d,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                    """.formatted(count, count))
                                .addHeader("Content-Type", "application/json");
                    } catch (Exception e) {
                        return new MockResponse().setResponseCode(500).setBody(e.getMessage());
                    }
                }
            });

            SymbolWorker worker = createWorker(server, "EURUSD", 1);
            worker.start();
            worker.stop();

            worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));

            assertThat(total.get()).isEqualTo(0);
        }
    }
}
