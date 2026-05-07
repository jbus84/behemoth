package com.behemoth.jforex.core;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.AccountSnapshotRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeOpenRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeUpdateRequestPayload;
import com.behemoth.jforex.state.ExecutionStateStore;
import com.behemoth.jforex.state.OcoGroupState;
import com.behemoth.jforex.worker.SymbolWorker;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class BehemothStrategyCore {
    private final JForexSessionConfig sessionConfig;
    private final PythonPredictionClient predictionClient;
    private final ExecutionStateStore stateStore;
    private final Stage14ArtifactWriter artifactWriter;
    private final JForexMetrics metrics;
    private final ExecutionPort executionPort;
    private final Map<String, SymbolRuntimeState> symbolStates = new LinkedHashMap<>();
    private final Map<String, SymbolWorker> symbolWorkers = new LinkedHashMap<>();
    /** Maps order label → fill context so handleFill can pass real values to /trades/open. */
    private final Map<String, PendingFillContext> pendingFills = new ConcurrentHashMap<>();
    /** Maps scan_id → order label so CLOSE_MARKET can look up the JForex order by label. */
    private final Map<String, String> scanToOrderLabel = new ConcurrentHashMap<>();

    public BehemothStrategyCore(
            JForexSessionConfig sessionConfig,
            PythonPredictionClient predictionClient,
            ExecutionStateStore stateStore,
            Stage14ArtifactWriter artifactWriter,
            JForexMetrics metrics,
            ExecutionPort executionPort
    ) {
        this.sessionConfig = Objects.requireNonNull(sessionConfig, "sessionConfig");
        this.predictionClient = Objects.requireNonNull(predictionClient, "predictionClient");
        this.stateStore = Objects.requireNonNull(stateStore, "stateStore");
        this.artifactWriter = Objects.requireNonNull(artifactWriter, "artifactWriter");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.executionPort = Objects.requireNonNull(executionPort, "executionPort");
    }

    public void start(List<RuntimeInstrument> instruments) {
        Set<String> subscribed = new LinkedHashSet<>();
        for (RuntimeInstrument instrument : instruments) {
            symbolStates.put(instrument.symbol(), new SymbolRuntimeState(instrument));
            SymbolWorker worker = new SymbolWorker(
                    instrument.symbol(),
                    sessionConfig,
                    predictionClient,
                    metrics,
                    artifactWriter,
                    actionCallbacks
            );
            symbolWorkers.put(instrument.symbol(), worker);
            worker.start();
            subscribed.add(instrument.symbol());
            artifactWriter.markOperationalStep(instrument.symbol(), "strategy_started", true, sessionConfig.runId());
            artifactWriter.markOperationalStep(instrument.symbol(), "subscribed", true, "instrument subscribed");
            refreshActiveOcoGauge(instrument.symbol());
        }
        try {
            predictionClient.feedStatus();
            for (String symbol : subscribed) {
                artifactWriter.markOperationalStep(symbol, "feed_status", true, "python runtime reachable");
            }
        } catch (RuntimeException exc) {
            for (String symbol : subscribed) {
                artifactWriter.markOperationalStep(symbol, "feed_status", false, exc.getMessage());
            }
            throw exc;
        }
    }

    public void seedClientTickSeq(String symbol, long lastClientTickSeq) {
        SymbolWorker worker = symbolWorkers.get(normalizeSymbol(symbol));
        if (worker != null) {
            worker.seedClientTickSeq(lastClientTickSeq);
        }
    }

    public void onTick(RuntimeTick tick) {
        SymbolWorker worker = symbolWorkers.get(normalizeSymbol(tick.symbol()));
        if (worker == null) {
            return;
        }
        worker.enqueue(tick);
    }

    public void drainWorker(String symbol) {
        SymbolWorker worker = symbolWorkers.get(normalizeSymbol(symbol));
        if (worker != null) {
            worker.drain();
        }
    }

    public long pendingCount(String symbol) {
        SymbolWorker worker = symbolWorkers.get(normalizeSymbol(symbol));
        return worker == null ? 0L : worker.pendingCount();
    }

    public void setEntriesAllowed(String symbol, boolean allowed) {
        SymbolRuntimeState state = symbolStates.get(normalizeSymbol(symbol));
        if (state == null) {
            throw new IllegalArgumentException("Unknown symbol: " + normalizeSymbol(symbol));
        }
        state.entriesAllowed = allowed;
    }

    public void onOrderEvent(OrderEvent event) {
        if (event == null) {
            return;
        }
        switch (event.type()) {
            case SUBMIT_OK -> {
                metrics.recordOrderSubmitted(event.symbol(), event.orderLabel());
            }
            case SUBMIT_REJECTED, FILL_REJECTED, CHANGE_REJECTED -> {
                metrics.recordOrderReject(event.symbol(), event.type().name());
                artifactWriter.markOperationalStep(event.symbol(), "order_rejected", false, event.detail());
            }
            case FILL_OK -> handleFill(event);
            case CHANGE_OK -> {
                // Modification success acknowledged.
            }
            case CLOSE_OK -> handleClose(event);
            case CLOSE_REJECTED -> {
                metrics.recordOrderReject(event.symbol(), event.type().name());
                artifactWriter.recordTradeSyncFailure(event.symbol(), "order_close_rejected", event.detail());
            }
        }
    }

    public void onAccountSnapshot(double balance, double equity, Instant snapshotTs) {
        Instant ts = Objects.requireNonNull(snapshotTs, "snapshotTs");
        for (String symbol : symbolStates.keySet()) {
            try {
                predictionClient.accountSnapshot(new AccountSnapshotRequestPayload(
                        symbol,
                        balance,
                        equity,
                        ts,
                        sessionConfig.runId()
                ));
                metrics.recordAccountSnapshot(symbol, true);
                artifactWriter.markOperationalStep(symbol, "account_snapshot", true, "snapshot submitted");
            } catch (RuntimeException exc) {
                metrics.recordAccountSnapshot(symbol, false);
                artifactWriter.markOperationalStep(symbol, "account_snapshot", false, exc.getMessage());
            }
        }
    }

    public void stop() {
        for (SymbolWorker worker : symbolWorkers.values()) {
            worker.stop();
        }
        stateStore.persist();
        artifactWriter.writeReports(symbolStates.keySet(), stateStore.groups());
    }

    public Set<String> symbols() {
        return Set.copyOf(symbolStates.keySet());
    }

    private void handleFill(OrderEvent event) {
        Instant fillTs = Objects.requireNonNullElse(event.fillTimeUtc(), Instant.now());
        metrics.recordOrderFill(event.symbol(), event.orderLabel().contains("BUY") ? "BUY" : "SELL");
        artifactWriter.recordFill(event.symbol(), event.orderLabel(), event.orderLabel());

        PendingFillContext ctx = pendingFills.remove(event.orderLabel());
        String candidateUid = ctx != null ? ctx.candidateUid() : "";
        String reservationId = ctx != null ? ctx.reservationId() : "";
        int horizon = ctx != null ? ctx.horizon() : 0;

        try {
            predictionClient.openTrade(new TradeOpenRequestPayload(
                    event.symbol(),
                    candidateUid,
                    event.brokerOrderId(),
                    event.orderLabel().contains("BUY") ? "Buy" : "Sell",
                    event.openPrice(),
                    fillTs,
                    horizon,
                    reservationId,
                    sessionConfig.runId()
            ));
            artifactWriter.markOperationalStep(event.symbol(), "trade_open_synced", true, event.brokerOrderId());
        } catch (RuntimeException exc) {
            metrics.recordPythonSyncFailure(event.symbol(), "trade_open");
            artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_open_sync_failure", exc.getMessage());
        }
    }

    private void handleClose(OrderEvent event) {
        Instant closeTs = Objects.requireNonNullElse(event.closeTimeUtc(), Instant.now());
        metrics.recordOrderClose(event.symbol(), "CLOSED");

        try {
            predictionClient.updateTrade(new TradeUpdateRequestPayload(
                    event.symbol(),
                    event.brokerOrderId(),
                    "CLOSED",
                    event.closePrice(),
                    closeTs,
                    event.pnlPips(),
                    sessionConfig.runId(),
                    "BARRIER_MANAGER",
                    event.commission()
            ));
            artifactWriter.markOperationalStep(event.symbol(), "trade_update_synced", true, event.brokerOrderId());
        } catch (RuntimeException exc) {
            metrics.recordPythonSyncFailure(event.symbol(), "trade_update");
            artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_update_sync_failure", exc.getMessage());
        }
    }

    private void refreshActiveOcoGauge(String symbol) {
        int active = 0;
        for (OcoGroupState group : stateStore.groups()) {
            if (String.valueOf(group.symbol).equalsIgnoreCase(symbol) && group.isActive()) {
                active += 1;
            }
        }
        metrics.setActiveOcoGroups(symbol, active);
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }

    private final SymbolWorker.ActionCallbacks actionCallbacks = new SymbolWorker.ActionCallbacks() {
        @Override public boolean entriesAllowed(String symbol) {
            SymbolRuntimeState state = symbolStates.get(normalizeSymbol(symbol));
            return state != null && state.entriesAllowed;
        }

        @Override public OrderResult submitMarketOrder(OrderSubmissionRequest request) {
            String symbol = request.symbol();
            String side = request.side();
            String label = request.label();
            String scanId = request.scanId();
            scanToOrderLabel.put(scanId, label);
            pendingFills.put(label, new PendingFillContext(
                    request.candidateUid(),
                    request.reservationId(),
                    request.horizon()
            ));
            try {
                try (JForexMetrics.TimerContext ignored = metrics.startOrderSubmitTimer(symbol, side)) {
                    OrderResult result = executionPort.submitMarketOrder(request);
                    metrics.recordOrderSubmitted(symbol, side);
                    artifactWriter.markOperationalStep(symbol, "market_order_submitted", true, label);
                    return result;
                }
            } catch (RuntimeException exc) {
                pendingFills.remove(label);
                scanToOrderLabel.remove(scanId);
                metrics.recordOrderSubmitFailure(symbol, side);
                artifactWriter.markOperationalStep(symbol, "market_order_submit_failure", false, exc.getMessage());
                return new OrderResult("", "", request.reservationId());
            }
        }

        @Override public void closePositionByScanId(String symbol, String scanId, Instant now) {
            String orderLabel = scanToOrderLabel.remove(scanId);
            if (orderLabel != null) {
                try {
                    try (JForexMetrics.TimerContext ignored = metrics.startOrderSubmitTimer(symbol, "CLOSE")) {
                        executionPort.closePosition(symbol, orderLabel);
                    }
                    artifactWriter.markOperationalStep(symbol, "barrier_close_submitted", true, orderLabel);
                } catch (RuntimeException exc) {
                    artifactWriter.markOperationalStep(symbol, "barrier_close_failure", false, exc.getMessage());
                }
            } else {
                artifactWriter.markOperationalStep(symbol, "barrier_close_skipped_no_label", false,
                        "scan_id=" + scanId);
            }
        }
    };

    private static final class SymbolRuntimeState {
        private final RuntimeInstrument instrument;
        private boolean entriesAllowed = true;

        private SymbolRuntimeState(RuntimeInstrument instrument) {
            this.instrument = instrument;
        }
    }

    private record PendingFillContext(
            String candidateUid,
            String reservationId,
            int horizon
    ) {
    }
}
