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
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;

class SymbolWorkerAsyncHealthTest {

    private static final ObjectMapper MAPPER = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private static SymbolWorker createWorker(MockWebServer server, String symbol, int tickBatchSize) throws Exception {
        Path tempDir = Files.createTempDirectory("worker-async-health-test");
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
                Duration.ofSeconds(5),
                Duration.ofSeconds(5)
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
    void queueStaysNearEmptyAt50TicksPerSec() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            AtomicInteger total = new AtomicInteger(0);
            server.setDispatcher(new Dispatcher() {
                @Override public MockResponse dispatch(RecordedRequest request) {
                    try {
                        String path = request.getPath();
                        if ("/ticks/batch".equals(path)) {
                            String body = request.getBody().readUtf8();
                            TickBatchRequestPayload payload = MAPPER.readValue(body, TickBatchRequestPayload.class);
                            int count = payload.ticks().size();
                            total.addAndGet(count);
                            return new MockResponse()
                                    .setBody("""
                                        {"ok":true,"symbol":"EURUSD","ticks_received":%d,"accepted_count":%d,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                                        """.formatted(count, count))
                                    .addHeader("Content-Type", "application/json");
                        }
                        if ("/predict".equals(path)) {
                            return new MockResponse()
                                    .setBody("""
                                        {"ok":true,"symbol":"EURUSD","predictions":[],"actions":[],"completed_bar_ticks":[]}
                                        """)
                                    .addHeader("Content-Type", "application/json");
                        }
                        return new MockResponse().setResponseCode(404).setBody("unknown path: " + path);
                    } catch (Exception e) {
                        return new MockResponse().setResponseCode(500).setBody(e.getMessage());
                    }
                }
            });

            SymbolWorker worker = createWorker(server, "EURUSD", 1000);
            worker.start();

            CopyOnWriteArrayList<Long> pendingSamples = new CopyOnWriteArrayList<>();

            Thread sampler = new Thread(() -> {
                long samplerStartNs = System.nanoTime();
                for (int i = 0; i < 60; i++) {
                    pendingSamples.add(worker.pendingCount());
                    long nextSampleNs = samplerStartNs + (i + 1) * 100_000_000L;
                    while (System.nanoTime() < nextSampleNs) {
                        Thread.yield();
                    }
                }
            }, "pending-sampler");
            sampler.start();

            Instant base = Instant.parse("2025-01-01T00:00:00Z");
            long feedStartNs = System.nanoTime();
            for (int i = 0; i < 250; i++) {
                worker.enqueue(new RuntimeTick(
                        "EURUSD",
                        base.plusMillis(i * 20L),
                        1.1000 + (i % 100) * 0.0001,
                        1.1002 + (i % 100) * 0.0001
                ));
                long nextTickNs = feedStartNs + (i + 1) * 20_000_000L;
                while (System.nanoTime() < nextTickNs) {
                    Thread.yield();
                }
            }

            worker.drain();
            sampler.join();
            worker.stop();

            assertThat(total.get()).isEqualTo(250);

            long maxPending = pendingSamples.stream().mapToLong(Long::longValue).max().orElse(0);
            assertThat(maxPending).isLessThanOrEqualTo(5);

            List<Long> sorted = pendingSamples.stream().sorted().toList();
            long median = sorted.get(sorted.size() / 2);
            assertThat(median).isEqualTo(0);
        }
    }
}
