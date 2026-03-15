package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record RuntimeTick(
        String symbol,
        Instant timestamp,
        double bid,
        double ask
) {
    public RuntimeTick {
        symbol = symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase();
        timestamp = Objects.requireNonNull(timestamp, "timestamp");
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (bid <= 0.0 || ask <= 0.0 || ask < bid) {
            throw new IllegalArgumentException("invalid bid/ask");
        }
    }
}
