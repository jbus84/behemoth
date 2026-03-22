package com.behemoth.jforex.live;

import java.time.Instant;
import java.util.Objects;

public record SymbolReadinessSnapshot(
        String symbol,
        SymbolReadinessState state,
        boolean entriesAllowed,
        Instant parquetTailTsUtc,
        Instant bridgeStartTsUtc,
        Instant bridgeEndTsUtc,
        Instant bridgeLastRequestedToUtc,
        Instant lastIngestedTickTsUtc,
        long stalenessSeconds,
        int warmupBarCount100,
        boolean startupTimeoutReached,
        String lastFailureReason,
        Instant lastStateTransitionUtc
) {
    public SymbolReadinessSnapshot {
        symbol = normalizeSymbol(symbol);
        state = Objects.requireNonNull(state, "state");
        lastFailureReason = Objects.requireNonNullElse(lastFailureReason, "");
        if (stalenessSeconds < 0) {
            throw new IllegalArgumentException("stalenessSeconds must be >= 0");
        }
        if (warmupBarCount100 < 0) {
            throw new IllegalArgumentException("warmupBarCount100 must be >= 0");
        }
    }

    private static String normalizeSymbol(String symbol) {
        String normalized = Objects.requireNonNull(symbol, "symbol").trim().toUpperCase();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        return normalized;
    }
}
