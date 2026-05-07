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
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;

class SymbolWorkerStressTest {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static SymbolWorker createWorker(MockWebServer server, String symbol, int tickBatchSize) throws Exception {
        Path tempDir = Files.createTempDirectory("worker-stress-test");
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

    @Test
    void enqueueOneMillionTicks() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            AtomicInteger total = new AtomicInteger(0);
            Set<Long> seenClientTickSeq = ConcurrentHashMap.newKeySet();
            server.setDispatcher(new Dispatcher() {
                @Override public MockResponse dispatch(RecordedRequest request) {
                    try {
                        String body = request.getBody().readUtf8();
                        TickBatchRequestPayload payload = MAPPER.readValue(body, TickBatchRequestPayload.class);
                        int count = 0;
                        for (var tick : payload.ticks()) {
                            if (tick.clientTickSeq() != null && seenClientTickSeq.add(tick.clientTickSeq())) {
                                count++;
                            }
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

            SymbolWorker worker = createWorker(server, "EURUSD", 1000);
            worker.start();

            Instant base = Instant.parse("2025-01-01T00:00:00Z");
            long startMs = System.currentTimeMillis();

            for (int i = 0; i < 1_000_000; i++) {
                worker.enqueue(new RuntimeTick("EURUSD", base, 1.1000 + (i % 100) * 0.0001, 1.1002 + (i % 100) * 0.0001));
            }

            worker.drain();
            long elapsedMs = System.currentTimeMillis() - startMs;
            worker.stop();

            assertThat(total.get()).isEqualTo(1_000_000);
            assertThat(elapsedMs).isLessThan(60_000);
        }
    }

    @Test
    void queueAgeStaysLowUnderNormalLoad() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            AtomicInteger total = new AtomicInteger(0);
            Set<Long> seenClientTickSeq = ConcurrentHashMap.newKeySet();
            server.setDispatcher(new Dispatcher() {
                @Override public MockResponse dispatch(RecordedRequest request) {
                    try {
                        String body = request.getBody().readUtf8();
                        TickBatchRequestPayload payload = MAPPER.readValue(body, TickBatchRequestPayload.class);
                        int count = 0;
                        for (var tick : payload.ticks()) {
                            if (tick.clientTickSeq() != null && seenClientTickSeq.add(tick.clientTickSeq())) {
                                count++;
                            }
                        }
                        total.addAndGet(count);
                        Thread.sleep(1L);
                        return new MockResponse()
                                .setBody("""
                                    {"ok":true,"symbol":"EURUSD","ticks_received":%d,"accepted_count":%d,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                    """.formatted(count, count))
                                .addHeader("Content-Type", "application/json");
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return new MockResponse().setResponseCode(500).setBody("interrupted");
                    } catch (Exception e) {
                        return new MockResponse().setResponseCode(500).setBody(e.getMessage());
                    }
                }
            });

            SymbolWorker worker = createWorker(server, "EURUSD", 100);
            worker.start();

            Instant base = Instant.parse("2025-01-01T00:00:00Z");
            for (int i = 0; i < 10_000; i++) {
                worker.enqueue(new RuntimeTick("EURUSD", base, 1.1000 + (i % 100) * 0.0001, 1.1002 + (i % 100) * 0.0001));
            }

            worker.drain();
            worker.stop();

            assertThat(total.get()).isEqualTo(10_000);
        }
    }
}
