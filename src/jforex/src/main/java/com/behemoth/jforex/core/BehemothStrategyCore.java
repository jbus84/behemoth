package com.behemoth.jforex.core;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.domain.PredictionDecision;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonApiException;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.AccountSnapshotRequestPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.PredictRequestPayload;
import com.behemoth.jforex.runtime.dto.PredictionResponseItem;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.behemoth.jforex.runtime.dto.TickBatchResponsePayload;
import com.behemoth.jforex.runtime.dto.TickIngestResponsePayload;
import com.behemoth.jforex.runtime.dto.TradeOpenRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeTouchRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeUpdateRequestPayload;
import com.behemoth.jforex.state.ExecutionStateStore;
import com.behemoth.jforex.state.OcoGroupState;
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

    public void onTick(RuntimeTick tick) {
        SymbolRuntimeState state = symbolStates.get(normalizeSymbol(tick.symbol()));
        if (state == null) {
            return;
        }
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
        if (event == null || stateStore.findByOrderLabel(event.orderLabel()) == null) {
            return;
        }
        switch (event.type()) {
            case SUBMIT_OK -> handleSubmitOk(event);
            case SUBMIT_REJECTED, FILL_REJECTED, CHANGE_REJECTED -> handleReject(event);
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
        // Close positions that have reached their exit horizon. Runs before the predict call
        // so the candidateUid lifecycle is clear when hasActiveCandidateLifecycle is checked below.
        List<String> labelsToClose = new ArrayList<>();
        for (Map.Entry<String, PendingExit> e : state.pendingExits.entrySet()) {
            if (!completedBarTicks.contains(e.getValue().barTicks())) {
                continue;
            }
            long currentOrdinal = state.barOrdinalsByBarTicks.getOrDefault(
                    e.getValue().barTicks(), 0L);
            if (currentOrdinal - e.getValue().fillBarOrdinal() >= e.getValue().horizon()) {
                labelsToClose.add(e.getKey());
            }
        }
        for (String label : labelsToClose) {
            state.pendingExits.remove(label);
            try {
                executionPort.closePosition(state.instrument.symbol(), label);
            } catch (RuntimeException exc) {
                artifactWriter.markOperationalStep(
                        state.instrument.symbol(), "horizon_close_failure", false, exc.getMessage());
            }
        }
        Map<Integer, Long> barOrdinals = Map.copyOf(state.barOrdinalsByBarTicks);
        try (JForexMetrics.TimerContext ignored = metrics.startPredictTimer(state.instrument.symbol())) {
            List<PredictionResponseItem> predictions = predictionClient.predict(new PredictRequestPayload(
                    state.instrument.symbol(),
                    sessionConfig.riskEnabled(),
                    sessionConfig.requestedVolumeUnits(),
                    completedBarTicks,
                    sessionConfig.runId(),
                    barOrdinals
            ));
            int selected = (int) predictions.stream().filter(PredictionResponseItem::isSelected).count();
            int blocked = (int) predictions.stream().filter(PredictionResponseItem::riskBlocked).count();
            metrics.recordSelectedPredictions(state.instrument.symbol(), selected, blocked);
            artifactWriter.recordPredictCycle(
                    state.instrument.symbol(),
                    predictions.size(),
                    selected,
                    blocked,
                    completedBarTicks
            );
            for (PredictionResponseItem prediction : predictions) {
                if (!prediction.isExecutable(sessionConfig.riskEnabled())) {
                    continue;
                }
                if (stateStore.hasActiveCandidateLifecycle(state.instrument.symbol(), prediction.candidateUid())) {
                    continue;
                }
                if (state.lastTick == null) {
                    continue;
                }
                if (!state.entriesAllowed) {
                    continue;
                }
                submitOcoPlan(state, prediction.toDecision(sessionConfig.requestedVolumeUnits()));
            }
        } catch (PythonApiException exc) {
            if (exc.statusCode() == 422 && exc.detail().contains("Insufficient warmup bars")) {
                metrics.recordPredictWarmup(state.instrument.symbol());
                return;
            }
            metrics.recordPredictFailure(state.instrument.symbol());
            artifactWriter.recordPredictFailure(state.instrument.symbol(), exc.detail());
            throw exc;
        }
    }

    private void submitOcoPlan(SymbolRuntimeState state, PredictionDecision decision) {
        RuntimeTick lastTick = Objects.requireNonNull(state.lastTick, "lastTick");
        Instant placedAt = lastTick.timestamp();
        OcoOrderPlan plan = OcoOrderPlanner.build(
                decision,
                lastTick.bid(),
                lastTick.ask(),
                state.instrument.pipSize(),
                placedAt
        );
        OcoGroupState group = stateStore.registerPlannedGroup(
                state.instrument.symbol(),
                decision,
                plan,
                sessionConfig.runId(),
                placedAt,
                sessionConfig.nativeOcoEnabled()
        );
        refreshActiveOcoGauge(state.instrument.symbol());
        double amountMillions = sessionConfig.requestedVolumeUnits() / FX_UNITS_PER_MILLION;
        long goodTillTime = lastTick.timestamp().toEpochMilli() + (sessionConfig.orderTtlSeconds() * 1000L);
        try {
            executionPort.submitStopOrder(new OrderRequest(
                    state.instrument.symbol(),
                    plan.buyLeg().label(),
                    plan.buyLeg().side(),
                    plan.buyLeg().triggerPrice(),
                    plan.stopLimitRangePips(),
                    amountMillions,
                    goodTillTime,
                    plan.buyLeg().comment(),
                    placedAt,
                    state.instrument.pipSize()
            ));
        } catch (RuntimeException exc) {
            metrics.recordOrderSubmitFailure(state.instrument.symbol(), plan.buyLeg().side().name());
            stateStore.markRejected(plan.buyLeg().label(), exc.getMessage());
            artifactWriter.recordOrderSubmitFailure(state.instrument.symbol(), group.groupLabel, "buy_leg_submit:" + exc.getMessage());
            throw exc;
        }

        try {
            executionPort.submitStopOrder(new OrderRequest(
                    state.instrument.symbol(),
                    plan.sellLeg().label(),
                    plan.sellLeg().side(),
                    plan.sellLeg().triggerPrice(),
                    plan.stopLimitRangePips(),
                    amountMillions,
                    goodTillTime,
                    plan.sellLeg().comment(),
                    placedAt,
                    state.instrument.pipSize()
            ));
        } catch (RuntimeException exc) {
            metrics.recordOrderSubmitFailure(state.instrument.symbol(), plan.sellLeg().side().name());
            stateStore.markRejected(plan.sellLeg().label(), exc.getMessage());
            artifactWriter.recordOrderSubmitFailure(state.instrument.symbol(), group.groupLabel, "sell_leg_submit:" + exc.getMessage());
            try {
                executionPort.cancelOrder(state.instrument.symbol(), plan.buyLeg().label());
            } catch (RuntimeException cancelExc) {
                metrics.recordSiblingCancelFailure(state.instrument.symbol());
                artifactWriter.recordSiblingCancelFailure(state.instrument.symbol(), group.groupLabel, "orphan_buy_leg:" + cancelExc.getMessage());
            }
            throw exc;
        }

        if (sessionConfig.nativeOcoEnabled()) {
            try {
                executionPort.enableNativeOco(plan.buyLeg().label(), plan.sellLeg().label());
            } catch (RuntimeException ignored) {
                // Manual sibling cancel remains authoritative.
            }
        }
    }

    private void handleSubmitOk(OrderEvent event) {
        OcoGroupState group = stateStore.markSubmitAccepted(
                event.orderLabel(),
                event.brokerOrderId(),
                sessionConfig.requestedVolumeUnits() / FX_UNITS_PER_MILLION
        ).group();
        OcoGroupState.OcoLegState leg = group.legForLabel(event.orderLabel());
        metrics.recordOrderSubmitted(event.symbol(), leg == null ? "UNKNOWN" : leg.side);
        artifactWriter.recordOrderSubmitted(event.symbol(), group.groupLabel, event.orderLabel());
        refreshActiveOcoGauge(event.symbol());
    }

    private void handleReject(OrderEvent event) {
        metrics.recordOrderReject(event.symbol(), event.type().name());
        stateStore.markRejected(event.orderLabel(), event.detail());
        OcoGroupState group = stateStore.findByOrderLabel(event.orderLabel());
        artifactWriter.recordOrderSubmitFailure(
                event.symbol(),
                group == null ? event.orderLabel() : group.groupLabel,
                event.detail()
        );
    }

    private void handleFill(OrderEvent event) {
        Instant fillTs = Objects.requireNonNullElse(event.fillTimeUtc(), Instant.now());
        ExecutionStateStore.FillAction action = stateStore.markFilled(
                event.orderLabel(),
                event.brokerOrderId(),
                event.openPrice(),
                fillTs
        );
        metrics.recordOrderFill(event.symbol(), action.leg().side);
        artifactWriter.recordFill(event.symbol(), action.group().groupLabel, action.leg().label);
        if (action.lifecycleViolation()) {
            metrics.recordLifecycleViolation(event.symbol(), "double_fill_detected");
            artifactWriter.recordLifecycleViolation(event.symbol(), action.group().groupLabel, "double_fill_detected");
        }
        if (action.shouldNotifyTradeOpen()) {
            try {
                predictionClient.openTrade(new TradeOpenRequestPayload(
                        event.symbol(),
                        action.group().candidateUid,
                        event.brokerOrderId(),
                        action.leg().side,
                        event.openPrice(),
                        fillTs,
                        action.group().horizon,
                        action.group().reservationId,
                        sessionConfig.runId()
                ));
                stateStore.markTradeOpenSynced(event.orderLabel());
                artifactWriter.recordTradeOpenSync(event.symbol(), event.brokerOrderId());
            } catch (RuntimeException exc) {
                metrics.recordPythonSyncFailure(event.symbol(), "trade_open");
                artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_open_sync_failure", exc.getMessage());
            }
        }
        if (action.siblingLabelToCancel() != null) {
            metrics.recordSiblingCancelAttempt(event.symbol());
            artifactWriter.recordSiblingCancelAttempt(event.symbol(), action.group().groupLabel, action.siblingLabelToCancel());
            try {
                stateStore.markCancelRequested(action.siblingLabelToCancel());
                executionPort.cancelOrder(event.symbol(), action.siblingLabelToCancel());
            } catch (RuntimeException exc) {
                metrics.recordSiblingCancelFailure(event.symbol());
                artifactWriter.recordSiblingCancelFailure(event.symbol(), action.group().groupLabel, exc.getMessage());
                throw exc;
            }
        }
        // Register pending horizon exit so triggerPrediction closes this leg after horizon bars.
        SymbolRuntimeState fillState = symbolStates.get(normalizeSymbol(event.symbol()));
        if (fillState != null) {
            long fillBarOrdinal = fillState.barOrdinalsByBarTicks.getOrDefault(
                    action.group().barTicks, -1L);
            fillState.pendingExits.put(
                    event.orderLabel(),
                    new PendingExit(fillBarOrdinal, action.group().horizon, action.group().barTicks));
        }
        refreshActiveOcoGauge(event.symbol());
    }

    private void handleClose(OrderEvent event) {
        Instant closeTs = Objects.requireNonNullElse(event.closeTimeUtc(), Instant.now());
        ExecutionStateStore.CloseAction action = stateStore.markClosed(
                event.orderLabel(),
                event.closePrice(),
                closeTs,
                event.pnlPips()
        );
        metrics.recordOrderClose(event.symbol(), action.tradeStatus());
        if (action.shouldNotifyTouch()) {
            try {
                predictionClient.touchTrade(new TradeTouchRequestPayload(event.symbol(), event.brokerOrderId(), sessionConfig.runId()));
                if (stateStore.markTradeTouchSynced(event.orderLabel())) {
                    artifactWriter.recordTradeTouchSync(event.symbol(), event.brokerOrderId());
                }
            } catch (RuntimeException exc) {
                metrics.recordPythonSyncFailure(event.symbol(), "trade_touch");
                artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_touch_sync_failure", exc.getMessage());
            }
        }
        if (action.shouldNotifyTradeUpdate()) {
            try {
                predictionClient.updateTrade(new TradeUpdateRequestPayload(
                        event.symbol(),
                        event.brokerOrderId(),
                        action.tradeStatus(),
                        event.closePrice(),
                        closeTs,
                        event.pnlPips(),
                        sessionConfig.runId()
                ));
                if (stateStore.markTradeUpdateSynced(event.orderLabel())) {
                    artifactWriter.recordTradeUpdateSync(event.symbol(), event.brokerOrderId(), action.tradeStatus());
                }
            } catch (RuntimeException exc) {
                metrics.recordPythonSyncFailure(event.symbol(), "trade_update");
                artifactWriter.recordTradeSyncFailure(event.symbol(), "trade_update_sync_failure", exc.getMessage());
            }
        }
        // emit per-trade outcome for reconciliation
        if (action != null && action.group() != null && action.leg() != null) {
            double fillPrice = action.leg().fillPrice != null ? action.leg().fillPrice : Double.NaN;
            double pnlValue = event.pnlPips() != null ? event.pnlPips() : Double.NaN;
            artifactWriter.recordTradeOutcome(
                    event.symbol(),
                    action.group().groupLabel,
                    action.group().candidateUid != null ? action.group().candidateUid : "",
                    action.leg().label,
                    fillPrice,
                    event.closePrice(),
                    pnlValue
            );
        }
        // Remove pending exit — covers both strategy-initiated and broker-initiated closes.
        SymbolRuntimeState closeState = symbolStates.get(normalizeSymbol(event.symbol()));
        if (closeState != null) {
            closeState.pendingExits.remove(event.orderLabel());
        }
        refreshActiveOcoGauge(event.symbol());
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
        // 0-indexed count of bars closed per bar_ticks granularity since session start.
        // Incremented before each predict call so bar_ordinals[N] == N means "Nth bar just closed".
        private final Map<Integer, Long> barOrdinalsByBarTicks = new LinkedHashMap<>();
        // label → pending horizon exit registered at fill time; removed when position closes
        private final Map<String, PendingExit> pendingExits = new LinkedHashMap<>();

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

    private record PendingExit(long fillBarOrdinal, int horizon, int barTicks) {
    }
}
