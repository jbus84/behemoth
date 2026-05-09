package com.behemoth.jforex.core;

import java.time.Instant;

public record OrderIntent(
    String symbol,
    String scanId,
    String side,
    double amountMillions,
    String candidateUid,
    String reservationId,
    int horizon,
    Instant timestamp
) {
    public OrderIntent {
        if (symbol == null || symbol.isBlank()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (scanId == null || scanId.isBlank()) {
            throw new IllegalArgumentException("scanId must not be blank");
        }
        if (side == null || (!side.equalsIgnoreCase("BUY") && !side.equalsIgnoreCase("SELL"))) {
            throw new IllegalArgumentException("side must be BUY or SELL, got: " + side);
        }
        if (amountMillions <= 0.0) {
            throw new IllegalArgumentException("amountMillions must be > 0");
        }
        if (timestamp == null) {
            throw new IllegalArgumentException("timestamp must not be null");
        }
        symbol = symbol.trim().replace("/", "").toUpperCase();
        side = side.trim().toUpperCase();
        candidateUid = candidateUid == null ? "" : candidateUid.trim();
        reservationId = reservationId == null ? "" : reservationId.trim();
    }
}
