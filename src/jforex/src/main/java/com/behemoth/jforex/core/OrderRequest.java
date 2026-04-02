package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record OrderRequest(
        String symbol,
        String label,
        String side,
        double triggerPrice,
        double stopLimitRangePips,
        double amountMillions,
        long goodTillEpochMs,
        String comment,
        Instant submittedAtUtc,
        double pipSize
) {
    public OrderRequest {
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
        if (triggerPrice <= 0.0) {
            throw new IllegalArgumentException("triggerPrice must be > 0");
        }
        if (stopLimitRangePips < 0.0) {
            throw new IllegalArgumentException("stopLimitRangePips must be >= 0");
        }
        if (amountMillions <= 0.0) {
            throw new IllegalArgumentException("amountMillions must be > 0");
        }
        if (pipSize <= 0.0) {
            throw new IllegalArgumentException("pipSize must be > 0");
        }
    }
}
