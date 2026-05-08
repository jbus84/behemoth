package com.behemoth.jforex.live;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.observability.LiveReadinessMetrics;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.BackfillRequestPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.dukascopy.api.IContext;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

public final class LiveReadinessCoordinator implements AutoCloseable {
    private static final Path DEFAULT_TICK_ROOT = Path.of("/Users/danielfisher/Desktop/dukascopy_ticks");
    private static final Duration STATUS_WRITE_INTERVAL = Duration.ofSeconds(5);
    private static final Duration HEARTBEAT_INTERVAL = Duration.ofSeconds(1);
    private static final int PHASE_BAR_TICKS = 100;
    private static final int WARMUP_BAR_COUNT_THRESHOLD = 289;

    private final JForexSessionConfig sessionConfig;
    private final LiveReadinessMetrics metrics;
    private final Clock clock;
    private final Consumer<LiveReadinessSnapshot> statusWriter;
    private final WarmupLoaderPort warmupLoader;
    private final WarmupPublisherPort warmupPublisher;
    private final BridgeRuntimeFactory bridgeRuntimeFactory;
    private final boolean autoStartHeartbeatScheduler;
    private final Map<String, SymbolReadinessState> lastPublishedStates = new LinkedHashMap<>();
    private final Map<String, Boolean> lastPublishedTimeouts = new LinkedHashMap<>();
    private final HashSet<String> initializationInFlightSymbols = new HashSet<>();

    private ScheduledExecutorService scheduler;
    private ExecutorService startupExecutor;
    private SymbolReadinessRegistry registry;
    private BridgeRuntime bridgeRuntime;
    private BehemothStrategyCore core;
    private List<String> symbols = List.of();
    private Instant lastStatusWriteAt;
    private boolean initialized;
    private boolean liveReadinessActive;

    public LiveReadinessCoordinator(
            JForexSessionConfig sessionConfig,
            PythonPredictionClient predictionClient,
            LiveReadinessMetrics metrics
    ) {
        this(
                sessionConfig,
                metrics,
                Clock.systemUTC(),
                DEFAULT_TICK_ROOT,
                snapshot -> new LiveReadinessStatusWriter(
                        sessionConfig.reportDir().resolve("runtime").resolve("live_symbol_readiness.json"),
                        predictionClient.objectMapper(),
                        LiveReadinessStatusWriter.deploymentStateResolverForGovernanceDir(
                                Path.of(System.getenv().getOrDefault(
                                        "BEHEMOTH_GOVERNANCE_DIR",
                                        "configs/research/governance/oco"
                                ))
                        ),
                        RestartReconciliation.resolverForRuntimeDir(
                                sessionConfig.reportDir().resolve("runtime"),
                                predictionClient.objectMapper()
                        )
                ).write(snapshot),
                (symbol, bridgeAnchorTs) -> new HistoricalWarmupLoader().load(
                        sessionConfig,
                        DEFAULT_TICK_ROOT,
                        symbol,
                        bridgeAnchorTs
                ),
                (symbol, ticks, runId) -> predictionClient.backfill(
                        new BackfillRequestPayload(
                                symbol,
                                PHASE_BAR_TICKS,
                                ticks,
                                runId
                        )
                ),
                (context, registry) -> {
                    Objects.requireNonNull(context, "context");
                    BrokerBridgeLoader loader = new BrokerBridgeLoader(
                            new JForexBrokerHistoryPort(context.getHistory()),
                            predictionClient,
                            registry,
                            Clock.systemUTC()
                    );
                    return new BridgeRuntime() {
                        @Override
                        public void seedClientTickSeq(String symbol, long lastClientTickSeq) {
                            loader.seedClientTickSeq(symbol, lastClientTickSeq);
                        }

                        @Override
                        public BrokerBridgeLoader.BridgeResult bridge(BrokerBridgeLoader.BridgeConfig config) {
                            return loader.bridge(config);
                        }
                    };
                },
                true
        );
    }

    LiveReadinessCoordinator(
            JForexSessionConfig sessionConfig,
            LiveReadinessMetrics metrics,
            Clock clock,
            Path tickRoot,
            Consumer<LiveReadinessSnapshot> statusWriter,
            WarmupLoaderPort warmupLoader,
            WarmupPublisherPort warmupPublisher,
            BridgeRuntimeFactory bridgeRuntimeFactory,
            boolean startHeartbeatScheduler
    ) {
        this.sessionConfig = Objects.requireNonNull(sessionConfig, "sessionConfig");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.statusWriter = Objects.requireNonNull(statusWriter, "statusWriter");
        this.warmupLoader = Objects.requireNonNull(warmupLoader, "warmupLoader");
        this.warmupPublisher = Objects.requireNonNull(warmupPublisher, "warmupPublisher");
        this.bridgeRuntimeFactory = Objects.requireNonNull(bridgeRuntimeFactory, "bridgeRuntimeFactory");
        this.autoStartHeartbeatScheduler = startHeartbeatScheduler;
    }

    public synchronized void initialize(IContext context, BehemothStrategyCore core, List<String> symbols) {
        if (initialized) {
            throw new IllegalStateException("Live readiness coordinator already initialized");
        }
        this.core = Objects.requireNonNull(core, "core");
        this.symbols = normalizeSymbols(symbols);
        this.registry = SymbolReadinessRegistry.forSymbols(this.symbols, sessionConfig.liveFreshnessSeconds());
        this.initialized = true;
        this.liveReadinessActive = sessionConfig.liveReadinessEnabled();
        this.lastStatusWriteAt = null;
        this.lastPublishedStates.clear();
        this.lastPublishedTimeouts.clear();
        this.initializationInFlightSymbols.clear();

        if (!liveReadinessActive) {
            Instant now = clock.instant();
            for (String symbol : this.symbols) {
                registry.markReady(symbol, now, 0, now);
            }
            publishSnapshot(now, true);
            return;
        }

        this.bridgeRuntime = bridgeRuntimeFactory.create(context, registry);
        Instant now = clock.instant();
        publishSnapshot(now, true);

        startStartupExecutor();
        for (String symbol : this.symbols) {
            submitSymbolInitialization(symbol);
        }

        if (autoStartHeartbeatScheduler) {
            startHeartbeatScheduler();
        }
    }

    public synchronized void recordLiveTick(String symbol, Instant tickTs) {
        if (!initialized || !liveReadinessActive) {
            return;
        }
        registry.recordFreshTick(symbol, tickTs);
        registry.refreshFreshness(tickTs, sessionConfig.liveFreshnessSeconds());
        maybeRetryBridgeInitialization(symbol);
        publishSnapshot(tickTs, false);
    }

    public synchronized void onHeartbeat(Instant now) {
        if (!initialized || !liveReadinessActive) {
            return;
        }
        registry.refreshFreshness(now, sessionConfig.liveFreshnessSeconds());
        publishSnapshot(now, false);
    }

    public synchronized SymbolReadinessSnapshot snapshot(String symbol) {
        ensureInitialized();
        return registry.snapshot(symbol);
    }

    public synchronized boolean entriesAllowed(String symbol) {
        return snapshot(symbol).entriesAllowed();
    }

    @Override
    public synchronized void close() {
        if (!initialized) {
            return;
        }
        try {
            if (liveReadinessActive) {
                publishSnapshot(clock.instant(), true);
            }
        } finally {
            if (scheduler != null) {
                scheduler.shutdownNow();
                scheduler = null;
            }
            if (startupExecutor != null) {
                startupExecutor.shutdownNow();
                startupExecutor = null;
            }
        }
    }

    private void submitSymbolInitialization(String symbol) {
        Objects.requireNonNull(startupExecutor, "startupExecutor");
        if (!initializationInFlightSymbols.add(symbol)) {
            return;
        }
        startupExecutor.submit(() -> initializeSymbol(symbol));
    }

    private void initializeSymbol(String symbol) {
        Instant startedAt = clock.instant();
        try {
            WarmupSlice warmup = warmupLoader.load(symbol, startedAt);
            registry.markParquetWarming(symbol, startedAt, warmup.bridgeAnchorTs());
            publishSnapshot(clock.instant(), true);

            try {
                warmupPublisher.publish(symbol, toPayloads(symbol, warmup.ticks(), sessionConfig.runId()), sessionConfig.runId());
            } catch (RuntimeException exc) {
                // Backfill publish is an HTTP call to the Python API — transient failures
                // (e.g. 503 during server startup) are retryable, same as broker bridge errors.
                throw new RuntimeException("Broker bridge failed: backfill publish: " + exc.getMessage(), exc);
            }
            bridgeRuntime.seedClientTickSeq(symbol, warmup.ticks().size());

            registry.markBridging(symbol, clock.instant());
            publishSnapshot(clock.instant(), true);

            int initialWarmupBarCount100 = warmup.ticks().size() / PHASE_BAR_TICKS;
            BrokerBridgeLoader.BridgeConfig bridgeConfig = new BrokerBridgeLoader.BridgeConfig(
                    symbol,
                    warmup.bridgeAnchorTs(),
                    sessionConfig.runId(),
                    Duration.ofMinutes(sessionConfig.liveBridgeWindowMinutes()),
                    Duration.ofSeconds(sessionConfig.liveFreshnessSeconds()),
                    Duration.ofMinutes(sessionConfig.liveStartupBridgeTimeoutMinutes()),
                    WARMUP_BAR_COUNT_THRESHOLD,
                    initialWarmupBarCount100
            );
            BrokerBridgeLoader.BridgeResult bridgeResult = bridgeRuntime.bridge(bridgeConfig);
            if (bridgeResult.lastClientTickSeq() != null) {
                core.seedClientTickSeq(symbol, bridgeResult.lastClientTickSeq());
            }
            publishSnapshot(clock.instant(), true);
        } catch (RuntimeException exc) {
            registry.markErrorPaused(symbol, clock.instant(), "Live readiness startup failed: " + exc.getMessage());
            publishSnapshot(clock.instant(), true);
        } finally {
            synchronized (this) {
                initializationInFlightSymbols.remove(symbol);
            }
        }
    }

    private void maybeRetryBridgeInitialization(String symbol) {
        SymbolReadinessSnapshot snapshot = registry.snapshot(symbol);
        if (snapshot.state() != SymbolReadinessState.ERROR_PAUSED) {
            return;
        }
        if (snapshot.startupTimeoutReached()) {
            return;
        }
        if (!snapshot.lastFailureReason().startsWith("Broker bridge failed:")) {
            return;
        }
        submitSymbolInitialization(symbol);
    }

    private synchronized void publishSnapshot(Instant asOfUtc, boolean forceWrite) {
        LiveReadinessSnapshot snapshot = registry.liveSnapshot(asOfUtc, sessionConfig.runId());
        boolean stateChanged = syncMetricsAndCore(snapshot);
        boolean dueForWrite = lastStatusWriteAt == null
                || !asOfUtc.isBefore(lastStatusWriteAt.plus(STATUS_WRITE_INTERVAL));
        if (forceWrite || stateChanged || dueForWrite) {
            statusWriter.accept(snapshot);
            lastStatusWriteAt = asOfUtc;
        }
    }

    private boolean syncMetricsAndCore(LiveReadinessSnapshot snapshot) {
        boolean changed = false;
        for (SymbolReadinessSnapshot symbol : snapshot.symbols()) {
            SymbolReadinessState previousState = lastPublishedStates.putIfAbsent(symbol.symbol(), symbol.state());
            if (previousState != null && previousState != symbol.state()) {
                metrics.recordReadinessTransition(symbol.symbol(), previousState, symbol.state());
                lastPublishedStates.put(symbol.symbol(), symbol.state());
                changed = true;
            }

            Boolean previousTimeout = lastPublishedTimeouts.putIfAbsent(symbol.symbol(), symbol.startupTimeoutReached());
            if ((previousTimeout == null || !previousTimeout) && symbol.startupTimeoutReached()) {
                metrics.recordReadinessTimeout(symbol.symbol());
                lastPublishedTimeouts.put(symbol.symbol(), true);
                changed = true;
            }

            metrics.setReadinessState(symbol.symbol(), symbol.state());
            metrics.setEntriesAllowed(symbol.symbol(), symbol.entriesAllowed());
            metrics.setTickStalenessSeconds(symbol.symbol(), symbol.stalenessSeconds());

            if (core != null) {
                core.setEntriesAllowed(symbol.symbol(), symbol.entriesAllowed());
            }
        }
        return changed;
    }

    private void startStartupExecutor() {
        if (startupExecutor != null) {
            return;
        }
        startupExecutor = Executors.newFixedThreadPool(Math.max(1, symbols.size()), runnable -> {
            Thread thread = new Thread(runnable, "jforex-live-readiness-startup");
            thread.setDaemon(true);
            return thread;
        });
    }
    private void startHeartbeatScheduler() {
        if (scheduler != null) {
            return;
        }
        scheduler = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "jforex-live-readiness-heartbeat");
            thread.setDaemon(true);
            return thread;
        });
        scheduler.scheduleAtFixedRate(
                () -> {
                    try {
                        onHeartbeat(clock.instant());
                    } catch (RuntimeException ignored) {
                        // Keep the scheduler alive; the coordinator state remains authoritative.
                    }
                },
                HEARTBEAT_INTERVAL.getSeconds(),
                HEARTBEAT_INTERVAL.getSeconds(),
                TimeUnit.SECONDS
        );
    }

    private static List<IncomingTickPayload> toPayloads(
            String symbol,
            List<com.behemoth.jforex.core.RuntimeTick> ticks,
            String runId
    ) {
        List<IncomingTickPayload> payloads = new ArrayList<>(ticks.size());
        long clientTickSeq = 1L;
        for (com.behemoth.jforex.core.RuntimeTick tick : ticks) {
            payloads.add(new IncomingTickPayload(
                    symbol,
                    tick.timestamp(),
                    tick.bid(),
                    tick.ask(),
                    1.0,
                    clientTickSeq++,
                    runId
            ));
        }
        return payloads;
    }

    private static List<String> normalizeSymbols(List<String> rawSymbols) {
        Objects.requireNonNull(rawSymbols, "symbols");
        List<String> normalized = rawSymbols.stream()
                .map(symbol -> {
                    String normalizedSymbol = Objects.requireNonNull(symbol, "symbol").trim().replace("/", "").toUpperCase();
                    if (normalizedSymbol.isEmpty()) {
                        throw new IllegalArgumentException("symbol must not be blank");
                    }
                    return normalizedSymbol;
                })
                .toList();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("At least one symbol is required");
        }
        return List.copyOf(normalized);
    }

    private void ensureInitialized() {
        if (!initialized || registry == null) {
            throw new IllegalStateException("Live readiness coordinator is not initialized");
        }
    }

    @FunctionalInterface
    interface WarmupLoaderPort {
        WarmupSlice load(String symbol, Instant bridgeAnchorTs);
    }

    @FunctionalInterface
    interface WarmupPublisherPort {
        void publish(String symbol, List<IncomingTickPayload> ticks, String runId);
    }

    @FunctionalInterface
    interface BridgeRuntimeFactory {
        BridgeRuntime create(IContext context, SymbolReadinessRegistry registry);
    }

    interface BridgeRuntime {
        void seedClientTickSeq(String symbol, long lastClientTickSeq);

        BrokerBridgeLoader.BridgeResult bridge(BrokerBridgeLoader.BridgeConfig config);
    }
}
