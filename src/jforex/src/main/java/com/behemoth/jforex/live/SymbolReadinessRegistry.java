package com.behemoth.jforex.live;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class SymbolReadinessRegistry {
    private static final long UNBOUNDED_FRESHNESS_THRESHOLD_SECONDS = Long.MAX_VALUE;

    private final Map<String, MutableSymbolReadiness> symbols;
    private long freshnessThresholdSeconds;

    private SymbolReadinessRegistry(Map<String, MutableSymbolReadiness> symbols, long freshnessThresholdSeconds) {
        this.symbols = symbols;
        this.freshnessThresholdSeconds = freshnessThresholdSeconds;
    }

    public static SymbolReadinessRegistry forSymbols(List<String> rawSymbols) {
        return forSymbols(rawSymbols, UNBOUNDED_FRESHNESS_THRESHOLD_SECONDS);
    }

    public static SymbolReadinessRegistry forSymbols(List<String> rawSymbols, long freshnessThresholdSeconds) {
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
        return new SymbolReadinessRegistry(
                symbols,
                requireNonNegative(freshnessThresholdSeconds, "freshnessThresholdSeconds")
        );
    }

    public synchronized void markParquetWarming(String rawSymbol, Instant transitionTsUtc, Instant parquetTailTsUtc) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.parquetTailTsUtc = Objects.requireNonNull(parquetTailTsUtc, "parquetTailTsUtc");
        symbol.startupTimeoutReached = false;
        symbol.lastFailureReason = "";
        symbol.transitionTo(SymbolReadinessState.PARQUET_WARMING, transitionTsUtc);
    }

    public synchronized void markBridging(String rawSymbol, Instant transitionTsUtc) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        Instant startedAt = Objects.requireNonNull(transitionTsUtc, "transitionTsUtc");
        symbol.bridgeStartTsUtc = startedAt;
        symbol.bridgeEndTsUtc = null;
        symbol.bridgeLastRequestedToUtc = null;
        symbol.startupTimeoutReached = false;
        symbol.lastFailureReason = "";
        symbol.transitionTo(SymbolReadinessState.BRIDGING, startedAt);
    }

    public synchronized void recordBridgeProgress(
            String rawSymbol,
            Instant bridgeLastRequestedToUtc,
            Instant latestBridgedTickTsUtc
    ) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.bridgeLastRequestedToUtc = Objects.requireNonNull(
                bridgeLastRequestedToUtc,
                "bridgeLastRequestedToUtc"
        );
        symbol.lastIngestedTickTsUtc = Objects.requireNonNull(latestBridgedTickTsUtc, "latestBridgedTickTsUtc");
        symbol.stalenessSeconds = 0L;
    }

    public synchronized void markBridgeComplete(String rawSymbol, Instant bridgeEndTsUtc) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        Instant completedAt = Objects.requireNonNull(bridgeEndTsUtc, "bridgeEndTsUtc");
        if (symbol.bridgeStartTsUtc == null) {
            symbol.bridgeStartTsUtc = completedAt;
        }
        symbol.bridgeEndTsUtc = completedAt;
        symbol.transitionTo(SymbolReadinessState.BRIDGING, completedAt);
    }

    public synchronized void markStartupTimeoutReached(String rawSymbol) {
        requireSymbol(rawSymbol).startupTimeoutReached = true;
    }

    public synchronized void markErrorPaused(String rawSymbol, Instant transitionTsUtc, String lastFailureReason) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.lastFailureReason = Objects.requireNonNullElse(lastFailureReason, "").trim();
        symbol.transitionTo(SymbolReadinessState.ERROR_PAUSED, transitionTsUtc);
    }

    public synchronized void markReady(
            String rawSymbol,
            Instant transitionTsUtc,
            int warmupBarCount100,
            Instant lastIngestedTickTsUtc
    ) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        Instant transitionAt = Objects.requireNonNull(transitionTsUtc, "transitionTsUtc");
        symbol.warmupBarCount100 = requireNonNegative(warmupBarCount100, "warmupBarCount100");
        symbol.lastIngestedTickTsUtc = Objects.requireNonNull(lastIngestedTickTsUtc, "lastIngestedTickTsUtc");
        symbol.stalenessSeconds = stalenessSeconds(transitionAt, lastIngestedTickTsUtc);
        symbol.lastFailureReason = "";
        SymbolReadinessState nextState = symbol.stalenessSeconds > freshnessThresholdSeconds
                ? SymbolReadinessState.STALE_PAUSED
                : SymbolReadinessState.READY;
        symbol.transitionTo(nextState, transitionAt);
    }

    public synchronized void recordFreshTick(String rawSymbol, Instant tickTsUtc) {
        MutableSymbolReadiness symbol = requireSymbol(rawSymbol);
        symbol.lastIngestedTickTsUtc = Objects.requireNonNull(tickTsUtc, "tickTsUtc");
        symbol.stalenessSeconds = 0L;
    }

    public synchronized void refreshFreshness(Instant asOfUtc) {
        refreshFreshnessInternal(asOfUtc, freshnessThresholdSeconds);
    }

    public synchronized void refreshFreshness(Instant asOfUtc, long freshnessThresholdSeconds) {
        long threshold = requireNonNegative(freshnessThresholdSeconds, "freshnessThresholdSeconds");
        this.freshnessThresholdSeconds = threshold;
        refreshFreshnessInternal(asOfUtc, threshold);
    }

    private void refreshFreshnessInternal(Instant asOfUtc, long freshnessThresholdSeconds) {
        Instant now = Objects.requireNonNull(asOfUtc, "asOfUtc");
        for (MutableSymbolReadiness symbol : symbols.values()) {
            if (symbol.lastIngestedTickTsUtc == null) {
                symbol.stalenessSeconds = 0L;
                continue;
            }
            symbol.stalenessSeconds = stalenessSeconds(now, symbol.lastIngestedTickTsUtc);
            if (symbol.state == SymbolReadinessState.READY
                    && symbol.stalenessSeconds > freshnessThresholdSeconds) {
                symbol.transitionTo(SymbolReadinessState.STALE_PAUSED, now);
            } else if (symbol.state == SymbolReadinessState.STALE_PAUSED
                    && symbol.stalenessSeconds <= freshnessThresholdSeconds) {
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
