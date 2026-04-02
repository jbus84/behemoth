package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.ExecutionPort;
import com.behemoth.jforex.core.OrderHandle;
import com.behemoth.jforex.core.OrderRequest;
import com.behemoth.jforex.core.RuntimeInstrument;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.observability.LiveReadinessMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.state.ExecutionStateStore;
import java.lang.reflect.Field;
import java.net.http.HttpClient;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.SAME_THREAD)
class LiveReadinessCoordinatorTest {
    @TempDir
    Path tempDir;

    @Test
    void sessionConfigExposesLiveReadinessDefaults() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false, testEnvironment());
        assertThat(cfg.liveReadinessEnabled()).isTrue();
        assertThat(cfg.liveWarmupTicks()).isEqualTo(30_000);
        assertThat(cfg.liveLookbackDays()).isEqualTo(31);
        assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(60);
        assertThat(cfg.liveFreshnessSeconds()).isEqualTo(30);
        assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(20);
    }

    @Test
    void sessionConfigDisablesLiveReadinessByDefaultInTesterMode() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(true, testEnvironmentForTesterMode());
        assertThat(cfg.liveReadinessEnabled()).isFalse();
    }

    @Test
    void sessionConfigParsesExplicitLiveReadinessOverrides() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false, testEnvironmentWithLiveOverrides());
        assertThat(cfg.liveReadinessEnabled()).isFalse();
        assertThat(cfg.liveWarmupTicks()).isEqualTo(12_345);
        assertThat(cfg.liveLookbackDays()).isEqualTo(7);
        assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(15);
        assertThat(cfg.liveFreshnessSeconds()).isEqualTo(45);
        assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(9);
    }

    @Test
    void coordinatorAllowsMixedReadyAndErrorPausedSymbols() throws Exception {
        JForexSessionConfig config = config(List.of("EURUSD", "GBPUSD"), true);
        RecordingStatusWriter statusWriter = new RecordingStatusWriter();
        RecordingLiveReadinessMetrics metrics = new RecordingLiveReadinessMetrics();
        Map<String, WarmupSlice> warmups = new LinkedHashMap<>();
        warmups.put("EURUSD", warmupSlice("EURUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075));
        warmups.put("GBPUSD", warmupSlice("GBPUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075));

        try (MockWebServer server = new MockWebServer()) {
            enqueueFeedStatusOk(server);
            BehemothStrategyCore core = buildCore(config, server);
            LiveReadinessCoordinator coordinator = new LiveReadinessCoordinator(
                    config,
                    metrics,
                    Clock.fixed(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC")),
                    tempDir.resolve("dukascopy_ticks"),
                    statusWriter,
                    (symbol, bridgeAnchorTs) -> warmups.get(symbol),
                    (symbol, ticks, runId) -> {
                    },
                    fakeBridgeRuntimeFactory(warmups),
                    false
            );

            coordinator.initialize(null, core, config.instruments());
            waitUntil(() -> coordinator.snapshot("EURUSD").state() == SymbolReadinessState.READY);
            waitUntil(() -> coordinator.snapshot("GBPUSD").state() == SymbolReadinessState.ERROR_PAUSED);

            assertThat(coordinator.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(coordinator.snapshot("GBPUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(coreEntriesAllowed(core, "EURUSD")).isTrue();
            assertThat(coreEntriesAllowed(core, "GBPUSD")).isFalse();
            assertThat(statusWriter.writeCount()).isGreaterThanOrEqualTo(3);
            assertThat(metrics.readinessStates.get("EURUSD")).isEqualTo(SymbolReadinessState.READY);
            assertThat(metrics.readinessStates.get("GBPUSD")).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
        }
    }

    @Test
    void staleFeedPausesNewEntriesOnly() throws Exception {
        JForexSessionConfig config = config(List.of("EURUSD"), true);
        RecordingStatusWriter statusWriter = new RecordingStatusWriter();
        RecordingLiveReadinessMetrics metrics = new RecordingLiveReadinessMetrics();
        Map<String, WarmupSlice> warmups = Map.of(
                "EURUSD",
                warmupSlice("EURUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075)
        );

        try (MockWebServer server = new MockWebServer()) {
            enqueueFeedStatusOk(server);
            BehemothStrategyCore core = buildCore(config, server);
            LiveReadinessCoordinator coordinator = new LiveReadinessCoordinator(
                    config,
                    metrics,
                    Clock.fixed(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC")),
                    tempDir.resolve("dukascopy_ticks"),
                    statusWriter,
                    (symbol, bridgeAnchorTs) -> warmups.get(symbol),
                    (symbol, ticks, runId) -> {
                    },
                    fakeBridgeRuntimeFactory(warmups),
                    false
            );

            coordinator.initialize(null, core, config.instruments());
            waitUntil(() -> coordinator.snapshot("EURUSD").state() == SymbolReadinessState.READY);
            coordinator.recordLiveTick("EURUSD", Instant.parse("2026-03-22T12:00:00Z"));
            coordinator.onHeartbeat(Instant.parse("2026-03-22T12:00:31Z"));

            assertThat(coordinator.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);
            assertThat(coreEntriesAllowed(core, "EURUSD")).isFalse();
            assertThat(coordinator.snapshot("EURUSD").stalenessSeconds()).isEqualTo(31);
            assertThat(metrics.readinessStates.get("EURUSD")).isEqualTo(SymbolReadinessState.STALE_PAUSED);
        }
    }

    @Test
    void coordinatorRewritesStatusSnapshotEveryFiveSecondsWithoutTicks() throws Exception {
        JForexSessionConfig config = config(List.of("EURUSD"), true);
        RecordingStatusWriter statusWriter = new RecordingStatusWriter();
        RecordingLiveReadinessMetrics metrics = new RecordingLiveReadinessMetrics();
        Map<String, WarmupSlice> warmups = Map.of(
                "EURUSD",
                warmupSlice("EURUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075)
        );

        try (MockWebServer server = new MockWebServer()) {
            enqueueFeedStatusOk(server);
            BehemothStrategyCore core = buildCore(config, server);
            LiveReadinessCoordinator coordinator = new LiveReadinessCoordinator(
                    config,
                    metrics,
                    Clock.fixed(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC")),
                    tempDir.resolve("dukascopy_ticks"),
                    statusWriter,
                    (symbol, bridgeAnchorTs) -> warmups.get(symbol),
                    (symbol, ticks, runId) -> {
                    },
                    fakeBridgeRuntimeFactory(warmups),
                    false
            );

            coordinator.initialize(null, core, config.instruments());
            waitUntil(() -> coordinator.snapshot("EURUSD").state() == SymbolReadinessState.READY);
            waitUntil(() -> statusWriter.writeCount() >= 3);
            int initialWrites = statusWriter.writeCount();
            coordinator.onHeartbeat(Instant.parse("2026-03-22T12:00:05Z"));
            coordinator.onHeartbeat(Instant.parse("2026-03-22T12:00:10Z"));

            assertThat(statusWriter.writeCount()).isEqualTo(initialWrites + 2);
        }
    }

    @Test
    void initializeDoesNotBlockOtherSymbolsBehindFirstBridge() throws Exception {
        JForexSessionConfig config = config(List.of("EURUSD", "GBPUSD"), true);
        RecordingStatusWriter statusWriter = new RecordingStatusWriter();
        RecordingLiveReadinessMetrics metrics = new RecordingLiveReadinessMetrics();
        Map<String, WarmupSlice> warmups = Map.of(
                "EURUSD",
                warmupSlice("EURUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075),
                "GBPUSD",
                warmupSlice("GBPUSD", Instant.parse("2026-03-22T11:59:59Z"), 30_075)
        );
        CountDownLatch eurusdBridgeStarted = new CountDownLatch(1);
        CountDownLatch releaseEurusdBridge = new CountDownLatch(1);

        try (MockWebServer server = new MockWebServer();
             ExecutorService executor = Executors.newSingleThreadExecutor()) {
            enqueueFeedStatusOk(server);
            BehemothStrategyCore core = buildCore(config, server);
            LiveReadinessCoordinator coordinator = new LiveReadinessCoordinator(
                    config,
                    metrics,
                    Clock.fixed(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC")),
                    tempDir.resolve("dukascopy_ticks"),
                    statusWriter,
                    (symbol, bridgeAnchorTs) -> warmups.get(symbol),
                    (symbol, ticks, runId) -> {
                    },
                    (context, registry) -> new LiveReadinessCoordinator.BridgeRuntime() {
                        @Override
                        public void seedClientTickSeq(String symbol, long lastClientTickSeq) {
                        }

                        @Override
                        public BrokerBridgeLoader.BridgeResult bridge(BrokerBridgeLoader.BridgeConfig bridgeConfig) {
                            if ("EURUSD".equals(bridgeConfig.symbol())) {
                                eurusdBridgeStarted.countDown();
                                try {
                                    if (!releaseEurusdBridge.await(1, TimeUnit.SECONDS)) {
                                        throw new IllegalStateException("timed out waiting to release EURUSD bridge");
                                    }
                                } catch (InterruptedException exc) {
                                    throw new RuntimeException(exc);
                                }
                            }
                            registry.markBridgeComplete(bridgeConfig.symbol(), bridgeConfig.parquetAnchorTsUtc());
                            registry.markReady(
                                    bridgeConfig.symbol(),
                                    bridgeConfig.parquetAnchorTsUtc(),
                                    bridgeConfig.initialWarmupBarCount100(),
                                    bridgeConfig.parquetAnchorTsUtc()
                            );
                            return new BrokerBridgeLoader.BridgeResult(
                                    true,
                                    bridgeConfig.initialWarmupBarCount100(),
                                    bridgeConfig.parquetAnchorTsUtc(),
                                    30_075L
                            );
                        }
                    },
                    false
            );

            Future<?> initializeFuture = executor.submit(() -> coordinator.initialize(null, core, config.instruments()));

            assertThat(eurusdBridgeStarted.await(1, TimeUnit.SECONDS)).isTrue();

            for (int i = 0; i < 50 && !initializeFuture.isDone(); i++) {
                Thread.sleep(10L);
            }
            assertThat(initializeFuture.isDone()).isTrue();

            for (int i = 0; i < 50 && coordinator.snapshot("GBPUSD").state() == SymbolReadinessState.COLD; i++) {
                Thread.sleep(10L);
            }
            assertThat(coordinator.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.BRIDGING);
            assertThat(coordinator.snapshot("GBPUSD").state()).isEqualTo(SymbolReadinessState.READY);

            releaseEurusdBridge.countDown();
            initializeFuture.get(1, TimeUnit.SECONDS);
        }
    }
    private LiveReadinessCoordinator.BridgeRuntimeFactory fakeBridgeRuntimeFactory(Map<String, WarmupSlice> warmups) {
        return (context, registry) -> new LiveReadinessCoordinator.BridgeRuntime() {
            @Override
            public void seedClientTickSeq(String symbol, long lastClientTickSeq) {
                // The fake bridge runtime only needs to preserve the coordinator contract.
            }

            @Override
            public BrokerBridgeLoader.BridgeResult bridge(BrokerBridgeLoader.BridgeConfig config) {
                String symbol = config.symbol();
                WarmupSlice warmup = warmups.get(symbol);
                if ("GBPUSD".equals(symbol)) {
                    registry.markStartupTimeoutReached(symbol);
                    registry.markErrorPaused(symbol, config.parquetAnchorTsUtc(), "bridge failed");
                    return new BrokerBridgeLoader.BridgeResult(false, config.initialWarmupBarCount100(), config.parquetAnchorTsUtc(), null);
                }
                registry.markBridgeComplete(symbol, config.parquetAnchorTsUtc());
                registry.markReady(
                        symbol,
                        config.parquetAnchorTsUtc(),
                        config.initialWarmupBarCount100(),
                        config.parquetAnchorTsUtc()
                );
                return new BrokerBridgeLoader.BridgeResult(
                        true,
                        config.initialWarmupBarCount100(),
                        config.parquetAnchorTsUtc(),
                        warmup == null ? null : 30_075L
                );
            }
        };
    }

    private BehemothStrategyCore buildCore(JForexSessionConfig config, MockWebServer server) {
        PythonPredictionClient predictionClient = new PythonPredictionClient(
                HttpClient.newHttpClient(),
                server.url("/").uri()
        );
        JForexMetrics metrics = JForexMetrics.start(config);
        Path statePath = tempDir.resolve("runtime").resolve("active_oco_state.json");
        ExecutionStateStore stateStore = new ExecutionStateStore(statePath, predictionClient.objectMapper());
        Stage14ArtifactWriter artifactWriter = new Stage14ArtifactWriter(tempDir.resolve("reports"), "test");
        ExecutionPort executionPort = new ExecutionPort() {
            @Override
            public OrderHandle submitStopOrder(OrderRequest request) {
                throw new UnsupportedOperationException("not used");
            }

            @Override
            public OrderHandle submitMarketOrder(com.behemoth.jforex.core.MarketOrderRequest request) {
                throw new UnsupportedOperationException("not used");
            }

            @Override
            public void enableNativeOco(String primaryLabel, String siblingLabel) {
                throw new UnsupportedOperationException("not used");
            }

            @Override
            public void cancelOrder(String symbol, String label) {
                throw new UnsupportedOperationException("not used");
            }

            @Override
            public void closePosition(String symbol, String label) {
                throw new UnsupportedOperationException("not used");
            }
        };
        BehemothStrategyCore core = new BehemothStrategyCore(
                config,
                predictionClient,
                stateStore,
                artifactWriter,
                metrics,
                executionPort
        );
        core.start(config.instruments().stream()
                .map(symbol -> new RuntimeInstrument(symbol, pipSize(symbol)))
                .toList());
        return core;
    }

    private static WarmupSlice warmupSlice(String symbol, Instant anchor, int tickCount) {
        List<RuntimeTick> ticks = new ArrayList<>(tickCount);
        Instant firstTick = anchor.minusSeconds(Math.max(1, tickCount));
        for (int i = 0; i < tickCount; i++) {
            Instant tickTs = firstTick.plusSeconds(i);
            ticks.add(new RuntimeTick(symbol, tickTs, 1.0850 + (i * 0.000001), 1.0851 + (i * 0.000001)));
        }
        return new WarmupSlice(anchor, ticks);
    }

    private static void enqueueFeedStatusOk(MockWebServer server) {
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""
                        {
                          "as_of_utc": "2026-03-22T12:00:00Z",
                          "governance_mode": "live",
                          "record_raw_ticks": true,
                          "symbols": []
                        }
                        """));
    }

    private static double pipSize(String symbol) {
        return symbol.endsWith("JPY") ? 0.01 : 0.0001;
    }

    private static boolean coreEntriesAllowed(BehemothStrategyCore core, String symbol) throws Exception {
        Field symbolStatesField = BehemothStrategyCore.class.getDeclaredField("symbolStates");
        symbolStatesField.setAccessible(true);
        Map<?, ?> symbolStates = (Map<?, ?>) symbolStatesField.get(core);
        Object state = symbolStates.get(symbol);
        Field entriesAllowedField = state.getClass().getDeclaredField("entriesAllowed");
        entriesAllowedField.setAccessible(true);
        return entriesAllowedField.getBoolean(state);
    }

    private static JForexSessionConfig config(List<String> symbols, boolean liveReadinessEnabled) {
        return new JForexSessionConfig(
                java.net.URI.create("http://127.0.0.1:8000"),
                java.net.URI.create("http://127.0.0.1/test.jnlp"),
                "user",
                "pass",
                "DU123",
                symbols,
                Instant.parse("2026-03-22T00:00:00Z"),
                Instant.parse("2026-03-22T00:01:00Z"),
                Path.of("build/test-reports"),
                "test-run",
                true,
                10_000.0,
                16,
                900L,
                false,
                60,
                false,
                "",
                0,
                liveReadinessEnabled,
                30_000,
                31,
                60,
                30,
                20
        );
    }

    private static Map<String, String> testEnvironment() {
        Map<String, String> environment = new HashMap<>();
        environment.put("BEHEMOTH_JFOREX_JNLP_URI", "http://127.0.0.1/test.jnlp");
        environment.put("BEHEMOTH_JFOREX_USERNAME", "user");
        environment.put("BEHEMOTH_JFOREX_PASSWORD", "pass");
        return Map.copyOf(environment);
    }

    private static Map<String, String> testEnvironmentWithLiveOverrides() {
        Map<String, String> environment = new HashMap<>(testEnvironment());
        environment.put("BEHEMOTH_JFOREX_LIVE_READINESS_ENABLED", "false");
        environment.put("BEHEMOTH_JFOREX_LIVE_WARMUP_TICKS", "12345");
        environment.put("BEHEMOTH_JFOREX_LIVE_LOOKBACK_DAYS", "7");
        environment.put("BEHEMOTH_JFOREX_LIVE_BRIDGE_WINDOW_MINUTES", "15");
        environment.put("BEHEMOTH_JFOREX_LIVE_FRESHNESS_SECONDS", "45");
        environment.put("BEHEMOTH_JFOREX_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES", "9");
        return Map.copyOf(environment);
    }

    private static Map<String, String> testEnvironmentForTesterMode() {
        Map<String, String> environment = new HashMap<>(testEnvironment());
        environment.put("BEHEMOTH_JFOREX_START_UTC", "2026-02-08T22:00:00Z");
        environment.put("BEHEMOTH_JFOREX_END_UTC", "2026-02-09T00:10:00Z");
        return Map.copyOf(environment);
    }

    private static void waitUntil(BooleanSupplier condition) throws InterruptedException {
        for (int i = 0; i < 100; i++) {
            if (condition.getAsBoolean()) {
                return;
            }
            Thread.sleep(10L);
        }
        assertThat(condition.getAsBoolean()).isTrue();
    }
    private static final class RecordingStatusWriter implements java.util.function.Consumer<LiveReadinessSnapshot> {
        private final List<LiveReadinessSnapshot> snapshots = new ArrayList<>();

        @Override
        public void accept(LiveReadinessSnapshot snapshot) {
            snapshots.add(snapshot);
        }

        private int writeCount() {
            return snapshots.size();
        }
    }

    private static final class RecordingLiveReadinessMetrics implements LiveReadinessMetrics {
        private final Map<String, SymbolReadinessState> readinessStates = new HashMap<>();
        private final Map<String, Boolean> entriesAllowed = new HashMap<>();
        private final Map<String, Long> stalenessSeconds = new HashMap<>();
        private final Map<String, Integer> transitions = new HashMap<>();
        private final Map<String, Integer> timeouts = new HashMap<>();

        @Override
        public void setReadinessState(String symbol, SymbolReadinessState state) {
            readinessStates.put(symbol, state);
        }

        @Override
        public void setEntriesAllowed(String symbol, boolean allowed) {
            entriesAllowed.put(symbol, allowed);
        }

        @Override
        public void setTickStalenessSeconds(String symbol, long stalenessSeconds) {
            this.stalenessSeconds.put(symbol, stalenessSeconds);
        }

        @Override
        public void recordReadinessTransition(String symbol, SymbolReadinessState fromState, SymbolReadinessState toState) {
            transitions.merge(symbol, 1, Integer::sum);
        }

        @Override
        public void recordReadinessTimeout(String symbol) {
            timeouts.merge(symbol, 1, Integer::sum);
        }
    }
}
