package com.behemoth.jforex.live;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record LiveReadinessSnapshot(
        Instant asOfUtc,
        String runId,
        int sessionTradableSymbolCount,
        int sessionTotalSymbolCount,
        List<SymbolReadinessSnapshot> symbols
) {
    public LiveReadinessSnapshot {
        asOfUtc = Objects.requireNonNull(asOfUtc, "asOfUtc");
        runId = Objects.requireNonNullElse(runId, "").trim();
        symbols = List.copyOf(Objects.requireNonNull(symbols, "symbols"));
        if (sessionTradableSymbolCount < 0) {
            throw new IllegalArgumentException("sessionTradableSymbolCount must be >= 0");
        }
        if (sessionTotalSymbolCount < 0) {
            throw new IllegalArgumentException("sessionTotalSymbolCount must be >= 0");
        }
    }
}
