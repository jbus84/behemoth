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
    }

    private JForexMetrics(JForexSessionConfig config) throws IOException {
        this.enabled = true;
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
