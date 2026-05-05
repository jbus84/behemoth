package com.behemoth.jforex.core;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonApiException;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.AccountSnapshotRequestPayload;
import com.behemoth.jforex.runtime.dto.BarrierActionPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.PredictRequestPayload;
import com.behemoth.jforex.runtime.dto.PredictResponsePayload;
import com.behemoth.jforex.runtime.dto.PredictionResponseItem;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.behemoth.jforex.runtime.dto.TickBatchResponsePayload;
import com.behemoth.jforex.runtime.dto.TickIngestResponsePayload;
import com.behemoth.jforex.runtime.dto.TradeOpenRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeUpdateRequestPayload;
import com.behemoth.jforex.state.ExecutionStateStore;
import com.behemoth.jforex.state.OcoGroupState;
import com.behemoth.jforex.worker.SymbolWorker;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class BehemothStrategyCore {
    private static final double FX_UNITS_PER_MILLION = 1_000_000.0;
    private static final int MAX_TICK_BATCH_TIMEOUT_RETRIES = 2;
    private static final long TICK_BATCH_RETRY_BACKOFF_MS = 250L;

    private final JForexSessionConfig sessionConfig;
    private final PythonPredictionClient predictionClient;
    private final ExecutionStateStore stateStore;
    private final Stage14ArtifactWriter artifactWriter;
    private final JForexMetrics metrics;
    private final ExecutionPort executionPort;
    private final Map<String, SymbolRuntimeState> symbolStates = new LinkedHashMap<>();
    private final Map<String, SymbolWorker> symbolWorkers = new LinkedHashMap<>();
    private final boolean useAsyncWorker = false;
    /** Maps order label → fill context so handleFill can pass real values to /trades/open. */
    private final Map<String, PendingFillContext> pendingFills = new LinkedHashMap<>();
    /** Maps scan_id → order label so CLOSE_MARKET can look up the JForex order by label. */
    private final Map<String, String> scanToOrderLabel = new LinkedHashMap<>();

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
            SymbolWorker worker = new SymbolWorker(instrument.symbol(), this::processTicksFromWorker);
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
        SymbolRuntimeState state = symbolStates.get(normalizeSymbol(symbol));
        if (state != null) {
            state.nextClientTickSeq = lastClientTickSeq + 1L;
        }
    }

    public void onTick(RuntimeTick tick) {
        SymbolWorker worker = symbolWorkers.get(normalizeSymbol(tick.symbol()));
        if (worker == null) {
            return;
        }
        worker.enqueue(tick);
        if (!useAsyncWorker) {
            worker.drain();
        }
    }

    private void processTicksFromWorker(String symbol, List<RuntimeTick> ticks) {
        SymbolRuntimeState state = symbolStates.get(normalizeSymbol(symbol));
        if (state == null) {
            return;
        }
        for (RuntimeTick tick : ticks) {
            state.pendingTicks.add(new IncomingTickPayload(
                    state.instrument.symbol(),
                    tick.timestamp(),
                    tick.bid(),
                    tick.ask(),
                    1.0,
                    state.nextClientTickSeq++,
                    sessionConfig.runId()
            ));
            state.lastTick = tick;
            metrics.recordTicksReceived(state.instrument.symbol(), 1);
            if (state.pendingTicks.size() >= sessionConfig.tickBatchSize()) {
                flushSymbol(state.instrument.symbol());
            }
        }
    }

    public void flushSymbol(String symbol) {
        SymbolRuntimeState state = symbolStates.get(normalizeSymbol(symbol));
        if (state == null || state.pendingTicks.isEmpty()) {
            return;
        }
        List<IncomingTickPayload> payload = List.copyOf(state.pendingTicks);
        state.pendingTicks.clear();
        TickBatchRequestPayload request = new TickBatchRequestPayload(
                state.instrument.symbol(),
                payload,
                sessionConfig.runId()
        );
        int attempt = 0;
        while (true) {
            try {
                TickBatchResponsePayload response = predictionClient.tickBatch(request);
                metrics.recordTickBatch(state.instrument.symbol(), response.acceptedCount(), response.droppedCount());
                artifactWriter.markOperationalStep(
                        state.instrument.symbol(),
                        "feed_status",
                        true,
                        "accepted=" + response.acceptedCount() + ";attempt=" + (attempt + 1)
                );
                if (response.barCompleted() && response.completedBarTicks() != null && !response.completedBarTicks().isEmpty()) {
                    triggerPrediction(state, response.completedBarTicks());
                }
                return;
            } catch (RuntimeException exc) {
                if (isRetriableTickBatchFailure(exc) && attempt < MAX_TICK_BATCH_TIMEOUT_RETRIES) {
                    attempt += 1;
                    sleepBeforeRetry();
                    continue;
                }
                if (isRetriableTickBatchFailure(exc)) {
                    TickIngestAggregate aggregate = ingestTicksIndividually(state, payload);
                    metrics.recordTickBatch(state.instrument.symbol(), aggregate.acceptedCount(), aggregate.droppedCount());
                    artifactWriter.markOperationalStep(
                            state.instrument.symbol(),
                            "feed_status",
                            true,
                            "accepted=" + aggregate.acceptedCount() + ";mode=single_tick_fallback"
                    );
                    if (!aggregate.completedBarTicks().isEmpty()) {
                        triggerPrediction(state, aggregate.completedBarTicks());
                    }
                    return;
                }
                state.pendingTicks.addAll(0, payload);
                artifactWriter.markOperationalStep(state.instrument.symbol(), "feed_status", false, exc.getMessage());
                throw exc;
            }
        }
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
        for (String symbol : List.copyOf(symbolStates.keySet())) {
            flushSymbol(symbol);
        }
        stateStore.persist();
        artifactWriter.writeReports(symbolStates.keySet(), stateStore.groups());
    }

    public Set<String> symbols() {
        return Set.copyOf(symbolStates.keySet());
    }

    private void triggerPrediction(SymbolRuntimeState state, List<Integer> completedBarTicks) {
        for (int barTick : completedBarTicks) {
            state.barOrdinalsByBarTicks.compute(barTick, (k, v) -> v == null ? 0L : v + 1L);
        }
        Map<Integer, Long> barOrdinals = Map.copyOf(state.barOrdinalsByBarTicks);
        try (JForexMetrics.TimerContext ignored = metrics.startPredictTimer(state.instrument.symbol())) {
            PredictResponsePayload response = predictionClient.predict(new PredictRequestPayload(
                    state.instrument.symbol(),
                    sessionConfig.riskEnabled(),
                    sessionConfig.requestedVolumeUnits(),
                    completedBarTicks,
                    sessionConfig.runId(),
                    barOrdinals
            ));
            List<PredictionResponseItem> predictions = response.predictions();

            int pythonSelected = 0;
            for (PredictionResponseItem p : predictions) {
                if (p.isSelected()) pythonSelected++;
            }
            Instant predictCloseTs = predictions.stream()
                    .map(PredictionResponseItem::closeTs)
                    .filter(Objects::nonNull)
                    .findFirst()
                    .orElseGet(() -> state.lastTick != null ? state.lastTick.timestamp() : Instant.now());
            metrics.recordSelectedPredictions(state.instrument.symbol(), pythonSelected, 0);
            artifactWriter.recordPredictCycle(
                    state.instrument.symbol(),
                    predictCloseTs,
                    predictions.size(),
                    pythonSelected,
                    response.actions().size(),
                    0,
                    List.of(),
                    completedBarTicks
            );

            executeActions(state, response.actions());
        } catch (PythonApiException exc) {
            if (exc.statusCode() == 422 && exc.detail().contains("Insufficient warmup bars")) {
                metrics.recordPredictWarmup(state.instrument.symbol());
                return;
            }
            metrics.recordPredictFailure(state.instrument.symbol());
            artifactWriter.recordPredictFailure(state.instrument.symbol(), exc.detail());
            return;
        }
    }

    private void executeActions(SymbolRuntimeState state, List<BarrierActionPayload> actions) {
        double amountMillions = sessionConfig.requestedVolumeUnits() / FX_UNITS_PER_MILLION;
        Instant now = state.lastTick != null ? state.lastTick.timestamp() : Instant.now();
        for (BarrierActionPayload action : actions) {
            if (action.isOpenMarket()) {
                if (!sessionConfig.newEntriesEnabled() || !state.entriesAllowed) {
                    metrics.recordEntryBlocked(action.symbol());
                    artifactWriter.markOperationalStep(
                            action.symbol(),
                            "entry_blocked_not_ready",
                            false,
                            sessionConfig.newEntriesEnabled()
                                    ? "entries not allowed in current readiness state"
                                    : "new entries disabled by restart eligibility"
                    );
                    continue;
                }
                String label = "BM_" + action.scanId() + "_" + action.side();
                scanToOrderLabel.put(action.scanId(), label);
                pendingFills.put(label, new PendingFillContext(
                        action.candidateUid() != null ? action.candidateUid() : "",
                        action.reservationId() != null ? action.reservationId() : "",
                        action.horizon()
                ));
                try {
                    executionPort.submitMarketOrder(new MarketOrderRequest(
                            action.symbol(),
                            label,
                            action.side(),
                            amountMillions,
                            "barrier_scan:" + action.scanId(),
                            now
                    ));
                    metrics.recordOrderSubmitted(action.symbol(), action.side());
                    artifactWriter.markOperationalStep(action.symbol(), "market_order_submitted", true, label);
                } catch (RuntimeException exc) {
                    pendingFills.remove(label);
                    metrics.recordOrderSubmitFailure(action.symbol(), action.side());
                    artifactWriter.markOperationalStep(action.symbol(), "market_order_submit_failure", false, exc.getMessage());
                }
            } else if (action.isCloseMarket()) {
                String orderLabel = scanToOrderLabel.remove(action.scanId());
                if (orderLabel != null) {
                    try {
                        executionPort.closePosition(action.symbol(), orderLabel);
                        artifactWriter.markOperationalStep(action.symbol(), "barrier_close_submitted", true, orderLabel);
                    } catch (RuntimeException exc) {
                        artifactWriter.markOperationalStep(action.symbol(), "barrier_close_failure", false, exc.getMessage());
                    }
                } else {
                    artifactWriter.markOperationalStep(action.symbol(), "barrier_close_skipped_no_label", false,
                            "scan_id=" + action.scanId() + " broker_pos_id=" + action.brokerPosId());
                }
            }
        }
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

    private static boolean isRetriableTickBatchFailure(RuntimeException exc) {
        if (!(exc instanceof PythonApiException apiException)) {
            return false;
        }
        if (apiException.statusCode() != 599) {
            return false;
        }
        String detail = String.valueOf(apiException.detail()).toLowerCase();
        return detail.contains("timed out") || detail.contains("timeout");
    }

    private static void sleepBeforeRetry() {
        try {
            Thread.sleep(TICK_BATCH_RETRY_BACKOFF_MS);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while retrying tick batch", exc);
        }
    }

    private TickIngestAggregate ingestTicksIndividually(SymbolRuntimeState state, List<IncomingTickPayload> payload) {
        int accepted = 0;
        int dropped = 0;
        Set<Integer> completedBarTicks = new LinkedHashSet<>();
        for (int i = 0; i < payload.size(); i++) {
            IncomingTickPayload tick = payload.get(i);
            try {
                TickIngestResponsePayload response = predictionClient.tick(tick);
                if (response.tickAccepted()) {
                    accepted += 1;
                } else {
                    dropped += 1;
                }
                if (response.barCompleted() && response.completedBarTicks() != null) {
                    completedBarTicks.addAll(response.completedBarTicks());
                }
            } catch (RuntimeException exc) {
                state.pendingTicks.addAll(0, payload.subList(i, payload.size()));
                artifactWriter.markOperationalStep(state.instrument.symbol(), "feed_status", false, exc.getMessage());
                throw exc;
            }
        }
        return new TickIngestAggregate(accepted, dropped, List.copyOf(completedBarTicks));
    }

    private static final class SymbolRuntimeState {
        private final RuntimeInstrument instrument;
        private final List<IncomingTickPayload> pendingTicks = new ArrayList<>();
        private long nextClientTickSeq = 1L;
        private boolean entriesAllowed = true;
        private RuntimeTick lastTick;
        private final Map<Integer, Long> barOrdinalsByBarTicks = new LinkedHashMap<>();

        private SymbolRuntimeState(RuntimeInstrument instrument) {
            this.instrument = instrument;
        }
    }

    private record TickIngestAggregate(
            int acceptedCount,
            int droppedCount,
            List<Integer> completedBarTicks
    ) {
    }

    private record PendingFillContext(
            String candidateUid,
            String reservationId,
            int horizon
    ) {
    }

}
