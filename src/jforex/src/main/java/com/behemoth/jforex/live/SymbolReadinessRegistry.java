package com.behemoth.jforex.live;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class SymbolReadinessRegistry {
    private final Map<String, MutableSymbolReadiness> symbols;

    private SymbolReadinessRegistry(Map<String, MutableSymbolReadiness> symbols) {
        this.symbols = symbols;
    }

    public static SymbolReadinessRegistry forSymbols(List<String> rawSymbols) {
        Objects.requireNonNull(rawSymbols, "rawSymbols");
        Map<String, MutableSymbolReadiness> symbols = new LinkedHashMap<>();
        for (String rawSymbol : rawSymbols) {
            String symbol = normalizeSymbol(rawSymbol);
            MutableSymbolReadiness previous = symbols.put(symbol, new MutableSymbolReadiness(symbol));
            if (previous != null) {
                throw new IllegalArgumentException("Duplicate symbol: " + symbol);
            }
        }
        if (symbols.isEmpty()) {
            throw new IllegalArgumentException("At least one symbol is required");
        }
        return new SymbolReadinessRegistry(symbols);
    }

    public synchronized void markReady(
            String rawSymbol,
            Instant transitionTsUtc,
            int warmupBarCount100,
            Instant lastIngestedTickTsUtc
    ) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.warmupBarCount100 = requireNonNegative(warmupBarCount100, "warmupBarCount100");
        symbol.lastIngestedTickTsUtc = Objects.requireNonNull(lastIngestedTickTsUtc, "lastIngestedTickTsUtc");
        symbol.stalenessSeconds = stalenessSeconds(transitionTsUtc, lastIngestedTickTsUtc);
        symbol.transitionTo(SymbolReadinessState.READY, transitionTsUtc);
    }

    public synchronized void recordFreshTick(String rawSymbol, Instant tickTsUtc) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.lastIngestedTickTsUtc = Objects.requireNonNull(tickTsUtc, "tickTsUtc");
    }

    public synchronized void refreshFreshness(Instant asOfUtc, long freshnessThresholdSeconds) {
        Instant now = Objects.requireNonNull(asOfUtc, "asOfUtc");
        long threshold = requireNonNegative(freshnessThresholdSeconds, "freshnessThresholdSeconds");
        for (MutableSymbolReadiness symbol : symbols.values()) {
            if (symbol.lastIngestedTickTsUtc == null) {
                symbol.stalenessSeconds = 0L;
                continue;
            }
            symbol.stalenessSeconds = stalenessSeconds(now, symbol.lastIngestedTickTsUtc);
            if (symbol.state == SymbolReadinessState.READY && symbol.stalenessSeconds > threshold) {
                symbol.transitionTo(SymbolReadinessState.STALE_PAUSED, now);
            } else if (symbol.state == SymbolReadinessState.STALE_PAUSED && symbol.stalenessSeconds <= threshold) {
                symbol.transitionTo(SymbolReadinessState.READY, now);
            }
        }
    }

    public synchronized SymbolReadinessSnapshot snapshot(String rawSymbol) {
        return requireSymbol(rawSymbol).snapshot();
    }

    public synchronized List<SymbolReadinessSnapshot> snapshots() {
        return symbols.values().stream()
                .map(MutableSymbolReadiness::snapshot)
                .toList();
    }

    public synchronized LiveReadinessSnapshot liveSnapshot(Instant asOfUtc, String runId) {
        List<SymbolReadinessSnapshot> snapshots = snapshots();
        int tradable = (int) snapshots.stream().filter(SymbolReadinessSnapshot::entriesAllowed).count();
        return new LiveReadinessSnapshot(asOfUtc, runId, tradable, snapshots.size(), snapshots);
    }

    private MutableSymbolReadiness requireSymbol(String rawSymbol) {
        String symbol = normalizeSymbol(rawSymbol);
        MutableSymbolReadiness readiness = symbols.get(symbol);
        if (readiness == null) {
            throw new IllegalArgumentException("Unknown symbol: " + symbol);
        }
        return readiness;
    }

    private static String normalizeSymbol(String rawSymbol) {
        String symbol = Objects.requireNonNull(rawSymbol, "symbol").trim().toUpperCase();
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        return symbol;
    }

    private static int requireNonNegative(int value, String fieldName) {
        if (value < 0) {
            throw new IllegalArgumentException(fieldName + " must be >= 0");
        }
        return value;
    }

    private static long requireNonNegative(long value, String fieldName) {
        if (value < 0L) {
            throw new IllegalArgumentException(fieldName + " must be >= 0");
        }
        return value;
    }

    private static long stalenessSeconds(Instant asOfUtc, Instant lastTickTsUtc) {
        return Math.max(0L, Duration.between(lastTickTsUtc, Objects.requireNonNull(asOfUtc, "asOfUtc")).getSeconds());
    }

    private static final class MutableSymbolReadiness {
        private final String symbol;
        private SymbolReadinessState state = SymbolReadinessState.COLD;
        private Instant parquetTailTsUtc;
        private Instant bridgeStartTsUtc;
        private Instant bridgeEndTsUtc;
        private Instant bridgeLastRequestedToUtc;
        private Instant lastIngestedTickTsUtc;
        private long stalenessSeconds;
        private int warmupBarCount100;
        private boolean startupTimeoutReached;
        private String lastFailureReason = "";
        private Instant lastStateTransitionUtc;

        private MutableSymbolReadiness(String symbol) {
            this.symbol = symbol;
        }

        private void transitionTo(SymbolReadinessState nextState, Instant transitionTsUtc) {
            state = Objects.requireNonNull(nextState, "nextState");
            lastStateTransitionUtc = Objects.requireNonNull(transitionTsUtc, "transitionTsUtc");
        }

        private SymbolReadinessSnapshot snapshot() {
            return new SymbolReadinessSnapshot(
                    symbol,
                    state,
                    state == SymbolReadinessState.READY,
                    parquetTailTsUtc,
                    bridgeStartTsUtc,
                    bridgeEndTsUtc,
                    bridgeLastRequestedToUtc,
                    lastIngestedTickTsUtc,
                    stalenessSeconds,
                    warmupBarCount100,
                    startupTimeoutReached,
                    lastFailureReason,
                    lastStateTransitionUtc
            );
        }
    }
}
