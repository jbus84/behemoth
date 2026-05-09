package com.behemoth.jforex.core;

import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public final class OrderBookingService {
    private final ExecutionPort executionPort;
    private final JForexMetrics metrics;
    private final Stage14ArtifactWriter artifactWriter;
    private final Map<String, OrderLifecycleHandler.PendingFillContext> pendingFills = new ConcurrentHashMap<>();
    private final Map<String, String> scanToOrderLabel = new ConcurrentHashMap<>();

    public OrderBookingService(ExecutionPort executionPort, JForexMetrics metrics, Stage14ArtifactWriter artifactWriter) {
        this.executionPort = Objects.requireNonNull(executionPort, "executionPort");
        this.metrics = Objects.requireNonNull(metrics, "metrics");
        this.artifactWriter = Objects.requireNonNull(artifactWriter, "artifactWriter");
    }

    public OrderResult submitMarketOrder(OrderIntent intent) {
        String label = formatLabel(intent.scanId(), intent.side());
        scanToOrderLabel.put(intent.scanId(), label);
        pendingFills.put(label, new OrderLifecycleHandler.PendingFillContext(
                intent.candidateUid(), intent.reservationId(), intent.horizon()));
        try {
            try (JForexMetrics.TimerContext ignored = metrics.startOrderSubmitTimer(intent.symbol(), intent.side())) {
                OrderResult result = executionPort.submitMarketOrder(toRequest(intent, label));
                metrics.recordOrderSubmitted(intent.symbol(), intent.side());
                artifactWriter.markOperationalStep(intent.symbol(), "market_order_submitted", true, label);
                return result;
            }
        } catch (RuntimeException exc) {
            pendingFills.remove(label);
            scanToOrderLabel.remove(intent.scanId());
            metrics.recordOrderSubmitFailure(intent.symbol(), intent.side());
            artifactWriter.markOperationalStep(intent.symbol(), "market_order_submit_failure", false, exc.getMessage());
            return new OrderResult("", "", intent.reservationId());
        }
    }

    public void closePositionByScanId(String symbol, String scanId, Instant now) {
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
            artifactWriter.markOperationalStep(symbol, "barrier_close_skipped_no_label", false, "scan_id=" + scanId);
        }
    }

    public Map<String, OrderLifecycleHandler.PendingFillContext> pendingFills() {
        return pendingFills;
    }

    public String orderLabelForScan(String scanId) {
        return scanToOrderLabel.get(scanId);
    }

    private static String formatLabel(String scanId, String side) {
        return "BM_" + scanId + "_" + side;
    }

    private static OrderSubmissionRequest toRequest(OrderIntent intent, String label) {
        return new OrderSubmissionRequest(
                intent.symbol(),
                label,
                intent.scanId(),
                intent.candidateUid(),
                intent.side(),
                intent.amountMillions(),
                intent.horizon(),
                intent.reservationId(),
                0.0,
                0.0,
                intent.timestamp()
        );
    }
}
