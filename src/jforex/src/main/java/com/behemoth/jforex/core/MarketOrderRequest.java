package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record MarketOrderRequest(
        String symbol,
        String label,
        String side,
        double amountMillions,
        String comment,
        Instant submittedAtUtc
) {
    public MarketOrderRequest {
        symbol = symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase();
        label = Objects.requireNonNull(label, "label").trim();
        side = Objects.requireNonNull(side, "side").trim().toUpperCase();
        comment = Objects.requireNonNullElse(comment, "");
        submittedAtUtc = Objects.requireNonNull(submittedAtUtc, "submittedAtUtc");
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (label.isEmpty()) {
            throw new IllegalArgumentException("label must not be blank");
        }
        if (!side.equals("BUY") && !side.equals("SELL")) {
            throw new IllegalArgumentException("side must be BUY or SELL, got: " + side);
        }
        if (amountMillions <= 0.0) {
            throw new IllegalArgumentException("amountMillions must be > 0");
        }
    }
}
