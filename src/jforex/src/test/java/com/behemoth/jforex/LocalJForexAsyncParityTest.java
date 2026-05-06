package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;

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
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.TimeZone;
import java.util.concurrent.atomic.AtomicInteger;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@EnabledIfSystemProperty(named = "behemoth.runAsyncParity", matches = "true")
class LocalJForexAsyncParityTest {

    @Test
    void asyncPathMatchesSyncBaseline() throws Exception {
        Path tempDir = Files.createTempDirectory("async-parity-test");
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("ticks.parquet");

        // 1. Create synthetic parquet fixture with 1000 ticks using DuckDB JDBC
        String parquetPath = parquetFile.toAbsolutePath().toString().replace("\\", "\\\\").replace("'", "''");
        try (Connection conn = DriverManager.getConnection("jdbc:duckdb:")) {
            try (Statement st = conn.createStatement()) {
                st.execute(
                    "COPY ("
                        + "SELECT TIMESTAMP '2025-07-07 00:00:00' + (i * INTERVAL 1 SECOND) AS timestamp,"
                        + " 1.08500 + (i * 0.000001) AS bid,"
                        + " 1.08510 + (i * 0.000001) AS ask"
                        + " FROM range(1000) AS t(i)"
                        + ") TO '" + parquetPath + "' (FORMAT PARQUET)"
                );
            }
        }

        // Load ticks from parquet
        List<RuntimeTick> ticks = new ArrayList<>();
        Calendar utcCal = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        try (Connection conn = DriverManager.getConnection("jdbc:duckdb:")) {
            try (Statement st = conn.createStatement();
                 ResultSet rs = st.executeQuery(
                     "SELECT timestamp, bid, ask FROM read_parquet('" + parquetPath + "') ORDER BY timestamp"
                 )) {
                while (rs.next()) {
                    ticks.add(new RuntimeTick(
                        "EURUSD",
                        rs.getTimestamp("timestamp", utcCal).toInstant(),
                        rs.getDouble("bid"),
                        rs.getDouble("ask")
                    ));
                }
            }
        }

        assertThat(ticks).hasSize(1000);

        // 2. Sync baseline: feed ticks with core.drainWorker() after each tick
        List<String> syncLabels;
        try (MockWebServer syncServer = new MockWebServer()) {
            setupDispatcher(syncServer);
            RecordingExecutionPort syncPort = new RecordingExecutionPort();
            BehemothStrategyCore syncCore = createCore(syncServer, tempDir.resolve("sync"), syncPort);
            syncCore.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

            for (RuntimeTick tick : ticks) {
                syncCore.onTick(tick);
                syncCore.drainWorker("EURUSD");
            }
            syncCore.stop();

            syncLabels = syncPort.marketOrders.stream().map(MarketOrderRequest::label).toList();
        }

        // 3. Async run: feed all ticks without drain, wait for pendingCount==0, then core.stop()
        List<String> asyncLabels;
        try (MockWebServer asyncServer = new MockWebServer()) {
            setupDispatcher(asyncServer);
            RecordingExecutionPort asyncPort = new RecordingExecutionPort();
            BehemothStrategyCore asyncCore = createCore(asyncServer, tempDir.resolve("async"), asyncPort);
            asyncCore.start(List.of(new RuntimeInstrument("EURUSD", 0.0001)));

            for (RuntimeTick tick : ticks) {
                asyncCore.onTick(tick);
            }

            int maxIterations = 12000; // up to ~120 seconds
            for (int i = 0; i < maxIterations && asyncCore.pendingCount("EURUSD") > 0; i++) {
                Thread.sleep(10L);
            }
            assertThat(asyncCore.pendingCount("EURUSD")).isEqualTo(0L);
            asyncCore.stop();

            asyncLabels = asyncPort.marketOrders.stream().map(MarketOrderRequest::label).toList();
        }

        // 4. Assert that async order labels match sync order labels exactly
        assertThat(asyncLabels).isEqualTo(syncLabels);
    }

    private static void setupDispatcher(MockWebServer server) {
        AtomicInteger tickBatchCount = new AtomicInteger(0);
        AtomicInteger predictCount = new AtomicInteger(0);
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath();
                if ("/runtime/feed/status".equals(path)) {
                    return new MockResponse()
                        .setBody("{\"as_of_utc\":\"2025-07-07T00:00:00Z\",\"governance_mode\":\"historical_auto\",\"record_raw_ticks\":false,\"symbols\":[]}")
                        .addHeader("Content-Type", "application/json");
                }
                if ("/ticks/batch".equals(path)) {
                    int count = tickBatchCount.incrementAndGet();
                    return new MockResponse()
                        .setBody(String.format(
                            "{\"ok\":true,\"symbol\":\"EURUSD\",\"ticks_received\":100,\"accepted_count\":100,\"dropped_count\":0,\"bar_completed\":true,\"completed_bar_ticks\":[100],\"symbol_tick_seq\":%d,\"last_tick_ts_utc\":\"2025-07-07T00:00:00Z\",\"last_client_tick_seq\":%d,\"bar_count\":%d}",
                            count, count, count
                        ))
                        .addHeader("Content-Type", "application/json");
                }
                if ("/predict".equals(path)) {
                    int count = predictCount.incrementAndGet();
                    if (count % 2 == 1) {
                        return new MockResponse()
                            .setBody(String.format(
                                "{\"predictions\":[{\"symbol\":\"EURUSD\",\"close_ts\":\"2025-07-07T00:00:00Z\",\"candidate_uid\":\"oco|EURUSD|100|h6|cand%d\",\"pred_prob\":0.78,\"threshold_exec\":0.61,\"selected_exec\":1,\"bar_ticks\":100,\"horizon\":6,\"barrier_pips\":2.0,\"cap_pips\":1.2,\"risk_blocked\":false,\"risk_reservation_id\":\"rid-%d\"}],\"actions\":[{\"type\":\"OPEN_MARKET\",\"symbol\":\"EURUSD\",\"candidate_uid\":\"oco|EURUSD|100|h6|cand%d\",\"scan_id\":\"scan-%03d\",\"side\":\"BUY\",\"reservation_id\":\"rid-%d\",\"broker_pos_id\":null,\"horizon\":6}]}",
                                count, count, count, count, count
                            ))
                            .addHeader("Content-Type", "application/json");
                    } else {
                        return new MockResponse()
                            .setBody("{\"predictions\":[],\"actions\":[]}")
                            .addHeader("Content-Type", "application/json");
                    }
                }
                return new MockResponse().setResponseCode(404).setBody("unknown path: " + path);
            }
        });
    }

    private static BehemothStrategyCore createCore(MockWebServer server, Path reportDir, ExecutionPort executionPort) throws Exception {
        Files.createDirectories(reportDir);
        JForexSessionConfig sessionConfig = new JForexSessionConfig(
            server.url("/").uri(),
            URI.create("http://example.test/jnlp"),
            "user",
            "pass",
            "",
            List.of("EURUSD"),
            Instant.parse("2025-07-07T00:00:00Z"),
            Instant.parse("2025-07-08T00:00:00Z"),
            reportDir,
            "run-test",
            false,
            10000.0,
            100,
            900L,
            false,
            60,
            false,
            "",
            0
        );
        PythonPredictionClient client = new PythonPredictionClient(
            HttpClient.newHttpClient(),
            server.url("/").uri(),
            Duration.ofSeconds(5),
            Duration.ofSeconds(5)
        );
        ExecutionStateStore stateStore = new ExecutionStateStore(
            reportDir.resolve("state.json"),
            client.objectMapper()
        );
        return new BehemothStrategyCore(
            sessionConfig,
            client,
            stateStore,
            new Stage14ArtifactWriter(reportDir, "test"),
            JForexMetrics.start(sessionConfig),
            executionPort
        );
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
