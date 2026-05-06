package com.behemoth.jforex.observability;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.live.SymbolReadinessState;
import io.prometheus.client.CollectorRegistry;
import io.prometheus.client.Counter;
import io.prometheus.client.Gauge;
import io.prometheus.client.Histogram;
import io.prometheus.client.exporter.HTTPServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.util.Objects;

/**
 * Prometheus metrics exporter for the Java-side JForex adapter.
 */
public final class JForexMetrics implements AutoCloseable, LiveReadinessMetrics {

    private static final JForexMetrics DISABLED = new JForexMetrics();
    private static volatile JForexMetrics LIVE_INSTANCE = null;

    private final boolean enabled;
    private final HTTPServer server;
    private final CollectorRegistry registry;
    private final Counter tickReceived;
    private final Counter tickAccepted;
    private final Counter tickDropped;
    private final Counter tickBatches;
    private final Gauge activeOcoGroups;
    private final Counter predictCalls;
    private final Counter predictWarmup422;
    private final Counter predictFailures;
    private final Counter selectedPredictions;
    private final Counter blockedPredictions;
    private final Histogram predictLatencySeconds;
    private final Counter ordersSubmitted;
    private final Counter orderSubmitFailures;
    private final Counter orderFills;
    private final Counter orderCloses;
    private final Counter orderRejects;
    private final Counter siblingCancelAttempts;
    private final Counter siblingCancelFailures;
    private final Counter lifecycleViolations;
    private final Counter accountSnapshots;
    private final Counter accountSnapshotFailures;
    private final Counter pythonSyncFailures;
    private final Gauge liveReadinessState;
    private final Gauge liveEntriesAllowed;
    private final Gauge liveTickStalenessSeconds;
    private final Counter liveReadinessTransitions;
    private final Counter liveReadinessTimeouts;
    private final Gauge workerQueueDepth;
    private final Gauge workerQueueAgeMs;
    private final Histogram workerBatchSize;
    private final Histogram workerDrainDurationMs;
    private final Histogram workerHttpPredictDurationMs;
    private final Histogram workerHttpTicksDurationMs;
    private final Histogram workerTickToPredictMs;
    private final Counter workerFatalTotal;
    private final Histogram orderSubmitDurationMs;
    private final Gauge strategyThreadOnTickNs;

    private JForexMetrics() {
        this.enabled = false;
        this.server = null;
        this.registry = null;
        this.tickReceived = null;
        this.tickAccepted = null;
        this.tickDropped = null;
        this.tickBatches = null;
        this.activeOcoGroups = null;
        this.predictCalls = null;
        this.predictWarmup422 = null;
        this.predictFailures = null;
        this.selectedPredictions = null;
        this.blockedPredictions = null;
        this.predictLatencySeconds = null;
        this.ordersSubmitted = null;
        this.orderSubmitFailures = null;
        this.orderFills = null;
        this.orderCloses = null;
        this.orderRejects = null;
        this.siblingCancelAttempts = null;
        this.siblingCancelFailures = null;
        this.lifecycleViolations = null;
        this.accountSnapshots = null;
        this.accountSnapshotFailures = null;
        this.pythonSyncFailures = null;
        this.liveReadinessState = null;
        this.liveEntriesAllowed = null;
        this.liveTickStalenessSeconds = null;
        this.liveReadinessTransitions = null;
        this.liveReadinessTimeouts = null;
        this.workerQueueDepth = null;
        this.workerQueueAgeMs = null;
        this.workerBatchSize = null;
        this.workerDrainDurationMs = null;
        this.workerHttpPredictDurationMs = null;
        this.workerHttpTicksDurationMs = null;
        this.workerTickToPredictMs = null;
        this.workerFatalTotal = null;
        this.orderSubmitDurationMs = null;
        this.strategyThreadOnTickNs = null;
    }

    private JForexMetrics(JForexSessionConfig config) throws IOException {
        this.enabled = true;
        LIVE_INSTANCE = this;
        this.registry = new CollectorRegistry();
        this.server = new HTTPServer(new InetSocketAddress(config.metricsHost(), config.metricsPort()), registry, true);
        this.tickReceived = counter("behemoth_jforex_ticks_received_total", "JForex ticks received by the adapter", "symbol");
        this.tickAccepted = counter("behemoth_jforex_ticks_accepted_total", "Ticks accepted by the Python runtime ingest path", "symbol");
        this.tickDropped = counter("behemoth_jforex_ticks_dropped_total", "Ticks dropped by the Python runtime ingest path", "symbol");
        this.tickBatches = counter("behemoth_jforex_tick_batches_total", "Tick batch posts to the Python runtime", "symbol");
        this.activeOcoGroups = Gauge.build()
                .name("behemoth_jforex_active_oco_groups")
                .help("Current active OCO groups tracked by the adapter")
                .labelNames("symbol")
                .register(registry);
        this.predictCalls = counter("behemoth_jforex_predict_calls_total", "Predict requests sent from JForex to Python", "symbol");
        this.predictWarmup422 = counter("behemoth_jforex_predict_warmup_422_total", "Predict calls rejected due to warmup", "symbol");
        this.predictFailures = counter("behemoth_jforex_predict_failures_total", "Predict calls that failed on the JForex side", "symbol");
        this.selectedPredictions = counter("behemoth_jforex_selected_predictions_total", "Selected predictions returned to the JForex adapter", "symbol");
        this.blockedPredictions = counter("behemoth_jforex_blocked_predictions_total", "Selected predictions blocked from execution by adapter-side gating", "symbol");
        this.predictLatencySeconds = Histogram.build()
                .name("behemoth_jforex_predict_latency_seconds")
                .help("Predict request latency from the JForex adapter")
                .labelNames("symbol")
                .buckets(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0)
                .register(registry);
        this.ordersSubmitted = counter("behemoth_jforex_orders_submitted_total", "JForex order submit acknowledgements", "symbol", "side");
        this.orderSubmitFailures = counter("behemoth_jforex_order_submit_failures_total", "Order submission failures recorded by the adapter", "symbol", "side");
        this.orderFills = counter("behemoth_jforex_order_fills_total", "Order fill acknowledgements", "symbol", "side");
        this.orderCloses = counter("behemoth_jforex_order_closes_total", "Order close acknowledgements", "symbol", "status");
        this.orderRejects = counter("behemoth_jforex_order_rejects_total", "Order-level reject messages", "symbol", "message_type");
        this.siblingCancelAttempts = counter("behemoth_jforex_sibling_cancel_attempts_total", "Manual sibling cancel attempts after first fill", "symbol");
        this.siblingCancelFailures = counter("behemoth_jforex_sibling_cancel_failures_total", "Manual sibling cancel failures", "symbol");
        this.lifecycleViolations = counter("behemoth_jforex_lifecycle_violations_total", "Lifecycle violations detected by the adapter", "symbol", "reason");
        this.accountSnapshots = counter("behemoth_jforex_account_snapshots_total", "Account snapshots published from JForex to Python", "symbol");
        this.accountSnapshotFailures = counter("behemoth_jforex_account_snapshot_failures_total", "Account snapshot publish failures", "symbol");
        this.pythonSyncFailures = counter("behemoth_jforex_python_sync_failures_total", "Lifecycle sync failures against the Python runtime", "symbol", "operation");
        this.liveReadinessState = Gauge.build()
                .name("behemoth_jforex_live_readiness_state")
                .help("Current live readiness state ordinal for the symbol")
                .labelNames("symbol")
                .register(registry);
        this.liveEntriesAllowed = Gauge.build()
                .name("behemoth_jforex_live_entries_allowed")
                .help("Whether new entries are currently allowed for the symbol")
                .labelNames("symbol")
                .register(registry);
        this.liveTickStalenessSeconds = Gauge.build()
                .name("behemoth_jforex_live_tick_staleness_seconds")
                .help("Current live tick staleness tracked by the readiness coordinator")
                .labelNames("symbol")
                .register(registry);
        this.liveReadinessTransitions = counter(
                "behemoth_jforex_live_readiness_transitions_total",
                "Readiness state transitions tracked by the coordinator",
                "symbol",
                "from_state",
                "to_state"
        );
        this.liveReadinessTimeouts = counter(
                "behemoth_jforex_live_readiness_timeouts_total",
                "Startup readiness timeouts tracked by the coordinator",
                "symbol"
        );
        this.workerQueueDepth = Gauge.build()
                .name("behemoth_worker_queue_depth")
                .help("Current depth of the symbol worker queue")
                .labelNames("symbol")
                .register(registry);
        this.workerQueueAgeMs = Gauge.build()
                .name("behemoth_worker_queue_age_ms")
                .help("Age in ms of the oldest tick in the worker queue at drain time")
                .labelNames("symbol")
                .register(registry);
        this.workerBatchSize = Histogram.build()
                .name("behemoth_worker_batch_size")
                .help("Number of ticks per worker drain batch")
                .labelNames("symbol")
                .buckets(1.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 512.0, 1024.0, 2048.0)
                .register(registry);
        this.workerDrainDurationMs = Histogram.build()
                .name("behemoth_worker_drain_duration_ms")
                .help("Time from take() to batch completion in the worker")
                .labelNames("symbol")
                .buckets(1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 5000.0)
                .register(registry);
        this.workerHttpPredictDurationMs = Histogram.build()
                .name("behemoth_worker_http_predict_duration_ms")
                .help("Wall time for /predict HTTP call from the worker thread")
                .labelNames("symbol")
                .buckets(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0)
                .register(registry);
        this.workerHttpTicksDurationMs = Histogram.build()
                .name("behemoth_worker_http_ticks_duration_ms")
                .help("Wall time for /ticks HTTP call from the worker thread")
                .labelNames("symbol")
                .buckets(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0)
                .register(registry);
        this.workerTickToPredictMs = Histogram.build()
                .name("behemoth_worker_tick_to_predict_ms")
                .help("Time from bar-completing tick epochMs to first byte of /predict response")
                .labelNames("symbol")
                .buckets(10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0)
                .register(registry);
        this.workerFatalTotal = counter("behemoth_worker_fatal_total", "Uncaught exceptions on worker thread", "symbol");
        this.orderSubmitDurationMs = Histogram.build()
                .name("behemoth_order_submit_duration_ms")
                .help("Wall time for IEngine.submitOrder")
                .labelNames("symbol", "action")
                .buckets(1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0)
                .register(registry);
        this.strategyThreadOnTickNs = Gauge.build()
                .name("behemoth_strategy_thread_onTick_ns")
                .help("Nanoseconds spent inside onTick on the strategy thread")
                .labelNames("symbol")
                .register(registry);
        int count = java.util.Collections.list(registry.metricFamilySamples()).size();
        System.out.println("[JForexMetrics] Registered " + count + " metric families");
    }

    public static JForexMetrics start(JForexSessionConfig config) {
        Objects.requireNonNull(config, "config");
        if (!config.metricsEnabled()) {
            return DISABLED;
        }
        try {
            return new JForexMetrics(config);
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to start JForex metrics server", exc);
        }
    }

    public TimerContext startPredictTimer(String symbol) {
        if (!enabled) {
            return TimerContext.disabled();
        }
        predictCalls.labels(symbol).inc();
        return new TimerContext(predictLatencySeconds.labels(symbol).startTimer());
    }

    public void recordTicksReceived(String symbol, int count) {
        if (enabled && count > 0) {
            tickReceived.labels(symbol).inc(count);
        }
    }

    public void recordTickBatch(String symbol, int accepted, int dropped) {
        if (!enabled) {
            return;
        }
        tickBatches.labels(symbol).inc();
        if (accepted > 0) {
            tickAccepted.labels(symbol).inc(accepted);
        }
        if (dropped > 0) {
            tickDropped.labels(symbol).inc(dropped);
        }
    }

    public void recordSelectedPredictions(String symbol, int selected, int blocked) {
        if (!enabled) {
            return;
        }
        if (selected > 0) {
            selectedPredictions.labels(symbol).inc(selected);
        }
        if (blocked > 0) {
            blockedPredictions.labels(symbol).inc(blocked);
        }
    }

    public void recordEntryBlocked(String symbol) {
        if (enabled) {
            blockedPredictions.labels(symbol).inc();
        }
    }

    public void recordPredictWarmup(String symbol) {
        if (enabled) {
            predictWarmup422.labels(symbol).inc();
        }
    }

    public void recordPredictFailure(String symbol) {
        if (enabled) {
            predictFailures.labels(symbol).inc();
        }
    }

    public void recordOrderSubmitted(String symbol, String side) {
        if (enabled) {
            ordersSubmitted.labels(symbol, side).inc();
        }
    }

    public void recordOrderSubmitFailure(String symbol, String side) {
        if (enabled) {
            orderSubmitFailures.labels(symbol, side).inc();
        }
    }

    public void recordOrderFill(String symbol, String side) {
        if (enabled) {
            orderFills.labels(symbol, side).inc();
        }
    }

    public void recordOrderClose(String symbol, String status) {
        if (enabled) {
            orderCloses.labels(symbol, status).inc();
        }
    }

    public void recordOrderReject(String symbol, String messageType) {
        if (enabled) {
            orderRejects.labels(symbol, messageType).inc();
        }
    }

    public void recordSiblingCancelAttempt(String symbol) {
        if (enabled) {
            siblingCancelAttempts.labels(symbol).inc();
        }
    }

    public void recordSiblingCancelFailure(String symbol) {
        if (enabled) {
            siblingCancelFailures.labels(symbol).inc();
        }
    }

    public void recordLifecycleViolation(String symbol, String reason) {
        if (enabled) {
            lifecycleViolations.labels(symbol, reason).inc();
        }
    }

    public void recordAccountSnapshot(String symbol, boolean success) {
        if (!enabled) {
            return;
        }
        if (success) {
            accountSnapshots.labels(symbol).inc();
        } else {
            accountSnapshotFailures.labels(symbol).inc();
        }
    }

    public void recordPythonSyncFailure(String symbol, String operation) {
        if (enabled) {
            pythonSyncFailures.labels(symbol, operation).inc();
        }
    }

    public void setActiveOcoGroups(String symbol, int activeCount) {
        if (enabled) {
            activeOcoGroups.labels(symbol).set(activeCount);
        }
    }

    @Override
    public void setReadinessState(String symbol, SymbolReadinessState state) {
        if (enabled) {
            liveReadinessState.labels(symbol).set(Objects.requireNonNull(state, "state").ordinal());
        }
    }

    @Override
    public void setEntriesAllowed(String symbol, boolean allowed) {
        if (enabled) {
            liveEntriesAllowed.labels(symbol).set(allowed ? 1.0 : 0.0);
        }
    }

    @Override
    public void setTickStalenessSeconds(String symbol, long stalenessSeconds) {
        if (enabled) {
            liveTickStalenessSeconds.labels(symbol).set(Math.max(0L, stalenessSeconds));
        }
    }

    @Override
    public void recordReadinessTransition(String symbol, SymbolReadinessState fromState, SymbolReadinessState toState) {
        if (enabled) {
            liveReadinessTransitions.labels(
                    symbol,
                    Objects.requireNonNull(fromState, "fromState").name(),
                    Objects.requireNonNull(toState, "toState").name()
            ).inc();
        }
    }

    @Override
    public void recordReadinessTimeout(String symbol) {
        if (enabled) {
            liveReadinessTimeouts.labels(symbol).inc();
        }
    }

    public void recordWorkerQueueDepth(String symbol, int depth) {
        if (enabled) {
            workerQueueDepth.labels(symbol).set(depth);
        }
    }

    public void recordWorkerQueueAgeMs(String symbol, long ageMs) {
        if (enabled) {
            workerQueueAgeMs.labels(symbol).set(ageMs);
        }
    }

    public void recordWorkerBatchSize(String symbol, int size) {
        if (enabled) {
            workerBatchSize.labels(symbol).observe(size);
        }
    }

    public void recordWorkerDrainDurationMs(String symbol, long durationMs) {
        if (enabled) {
            workerDrainDurationMs.labels(symbol).observe(durationMs);
        }
    }

    public TimerContext startWorkerHttpPredictTimer(String symbol) {
        if (!enabled) {
            return TimerContext.disabled();
        }
        return new TimerContext(workerHttpPredictDurationMs.labels(symbol).startTimer());
    }

    public TimerContext startWorkerHttpTicksTimer(String symbol) {
        if (!enabled) {
            return TimerContext.disabled();
        }
        return new TimerContext(workerHttpTicksDurationMs.labels(symbol).startTimer());
    }

    public void recordWorkerTickToPredictMs(String symbol, long durationMs) {
        if (enabled) {
            workerTickToPredictMs.labels(symbol).observe(durationMs);
        }
    }

    public void recordWorkerFatal(String symbol) {
        if (enabled) {
            workerFatalTotal.labels(symbol).inc();
        }
    }

    public TimerContext startOrderSubmitTimer(String symbol, String action) {
        if (!enabled) {
            return TimerContext.disabled();
        }
        return new TimerContext(orderSubmitDurationMs.labels(symbol, action).startTimer());
    }

    public void recordStrategyThreadOnTickNs(String symbol, long nanos) {
        if (enabled) {
            strategyThreadOnTickNs.labels(symbol).set(nanos);
        }
    }

    @Override
    public void close() {
        if (enabled && server != null) {
            server.stop();
        }
    }

    private Counter counter(String name, String help, String... labelNames) {
        return Counter.build().name(name).help(help).labelNames(labelNames).register(registry);
    }

    public static final class TimerContext implements AutoCloseable {
        private static final TimerContext DISABLED = new TimerContext(null);
        private final Histogram.Timer timer;

        private TimerContext(Histogram.Timer timer) {
            this.timer = timer;
        }

        public static TimerContext disabled() {
            return DISABLED;
        }

        @Override
        public void close() {
            if (timer != null) {
                timer.observeDuration();
            }
        }
    }
}
