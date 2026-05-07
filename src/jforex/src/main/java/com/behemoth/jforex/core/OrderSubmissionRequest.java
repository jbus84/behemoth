package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record OrderSubmissionRequest(
        String symbol,
        String label,
        String scanId,
        String candidateUid,
        String side,
        double amountMillions,
        int horizon,
        String reservationId,
        double entryPrice,
        double barrier,
        Instant submittedAtUtc
) {
    public OrderSubmissionRequest {
        symbol = symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase();
        label = Objects.requireNonNull(label, "label").trim();
        scanId = Objects.requireNonNull(scanId, "scanId").trim();
        candidateUid = Objects.requireNonNullElse(candidateUid, "").trim();
        side = Objects.requireNonNull(side, "side").trim().toUpperCase();
        reservationId = Objects.requireNonNullElse(reservationId, "").trim();
        submittedAtUtc = Objects.requireNonNull(submittedAtUtc, "submittedAtUtc");
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (label.isEmpty()) {
            throw new IllegalArgumentException("label must not be blank");
        }
        if (scanId.isEmpty()) {
            throw new IllegalArgumentException("scanId must not be blank");
        }
        if (!side.equals("BUY") && !side.equals("SELL")) {
            throw new IllegalArgumentException("side must be BUY or SELL, got: " + side);
        }
        if (amountMillions <= 0.0) {
            throw new IllegalArgumentException("amountMillions must be > 0");
        }
    }

    public MarketOrderRequest toMarketOrderRequest() {
        return new MarketOrderRequest(
                symbol,
                label,
                side,
                amountMillions,
                "barrier_scan:" + scanId,
                submittedAtUtc
        );
    }
}
