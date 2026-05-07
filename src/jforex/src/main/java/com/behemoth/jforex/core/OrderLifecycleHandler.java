package com.behemoth.jforex.core;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.TradeOpenRequestPayload;
import com.behemoth.jforex.runtime.dto.TradeUpdateRequestPayload;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public final class OrderLifecycleHandler {
    private final JForexSessionConfig sessionConfig;
    private final PythonPredictionClient predictionClient;
    private final Stage14ArtifactWriter artifactWriter;
    private final JForexMetrics metrics;
    private final Map<String, PendingFillContext> pendingFills;

    public OrderLifecycleHandler(
            JForexSessionConfig sessionConfig,
            PythonPredictionClient predictionClient,
            Stage14ArtifactWriter artifactWriter,
            JForexMetrics metrics,
            Map<String, PendingFillContext> pendingFills
    ) {
        this.sessionConfig = Objects.requireNonNull(sessionConfig, "sessionConfig");
        this.predictionClient = Objects.requireNonNull(predictionClient, "predictionClient");
        this.artifactWriter = Objects.requireNonNull(artifactWriter, "artifactWriter");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.pendingFills = Objects.requireNonNull(pendingFills, "pendingFills");
    }

    public void onOrderEvent(OrderEvent event) {
        if (event == null) {
            return;
        }
        switch (event.type()) {
            case SUBMIT_OK -> metrics.recordOrderSubmitted(event.symbol(), event.orderLabel());
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

    public record PendingFillContext(
            String candidateUid,
            String reservationId,
            int horizon
    ) {
    }
}
