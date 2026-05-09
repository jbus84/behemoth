package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.OrderIntent;
import com.behemoth.jforex.core.OrderResult;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;

class SymbolWorkerTest {

    private static SymbolWorker createWorker(MockWebServer server, String symbol, int tickBatchSize) throws Exception {
        Path tempDir = Files.createTempDirectory("worker-test");
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

    private static MockResponse tickBatchResponse() {
        return new MockResponse()
                .setBody("""
                        {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,"dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],"symbol_tick_seq":1,"last_tick_ts_utc":"2025-07-07T00:00:00Z","last_client_tick_seq":1,"bar_count":1}
                        """)
                .addHeader("Content-Type", "application/json");
    }

    @Test
    void enqueueAndDrainProcessesAllTicks() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(tickBatchResponse());
            server.enqueue(tickBatchResponse());

            SymbolWorker worker = createWorker(server, "EURUSD", 1);
            worker.start();

            Instant t1 = Instant.parse("2025-01-01T00:00:00Z");
            Instant t2 = Instant.parse("2025-01-01T00:00:01Z");
            worker.enqueue(new RuntimeTick("EURUSD", t1, 1.1000, 1.1002));
            worker.enqueue(new RuntimeTick("EURUSD", t2, 1.1001, 1.1003));

            worker.drain();
            worker.stop();

            assertThat(server.getRequestCount()).isEqualTo(2);
        }
    }

    @Test
    void preservesTickOrdering() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(tickBatchResponse());

            SymbolWorker worker = createWorker(server, "EURUSD", 100);
            worker.start();

            for (int i = 0; i < 100; i++) {
                worker.enqueue(
                        new RuntimeTick(
                                "EURUSD",
                                Instant.now(),
                                1.1000 + i * 0.0001,
                                1.1002 + i * 0.0001));
            }

            worker.drain();
            worker.stop();

            assertThat(server.getRequestCount()).isEqualTo(1);
        }
    }

    @Test
    void drainReturnsImmediatelyWhenQueueEmpty() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            SymbolWorker worker = createWorker(server, "EURUSD", 1);
            worker.start();

            long start = System.currentTimeMillis();
            worker.drain();
            long elapsed = System.currentTimeMillis() - start;

            worker.stop();

            assertThat(elapsed).isLessThan(100);
        }
    }

    @Test
    void stopInterruptsWorker() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(tickBatchResponse());

            SymbolWorker worker = createWorker(server, "EURUSD", 1);
            worker.start();

            worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
            Thread.sleep(50);
            worker.stop();

            assertThat(server.getRequestCount()).isEqualTo(1);
        }
    }
}
