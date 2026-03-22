package com.behemoth.jforex.live;

import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.FeedStatusResponsePayload;
import com.behemoth.jforex.runtime.dto.FeedStatusSymbolPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.behemoth.jforex.runtime.dto.TickBatchResponsePayload;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class BrokerBridgeLoader {
    static final Duration BRIDGE_WINDOW = Duration.ofMinutes(60);
    private static final Duration MIN_WINDOW = Duration.ofMinutes(1);

    private final BrokerHistoryPort historyPort;
    private final PythonPredictionClient predictionClient;
    private final SymbolReadinessRegistry registry;
    private final Clock clock;
    private final Map<String, Long> nextClientTickSeqBySymbol = new HashMap<>();

    public BrokerBridgeLoader(
            BrokerHistoryPort historyPort,
            PythonPredictionClient predictionClient,
            SymbolReadinessRegistry registry,
            Clock clock
    ) {
        this.historyPort = Objects.requireNonNull(historyPort, "historyPort");
        this.predictionClient = Objects.requireNonNull(predictionClient, "predictionClient");
        this.registry = Objects.requireNonNull(registry, "registry");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public synchronized void seedClientTickSeq(String rawSymbol, long lastClientTickSeq) {
        String symbol = normalizeSymbol(rawSymbol);
        if (lastClientTickSeq < 0L) {
            throw new IllegalArgumentException("lastClientTickSeq must be >= 0");
        }
        nextClientTickSeqBySymbol.put(symbol, lastClientTickSeq + 1L);
    }

    public BridgeResult bridge(BridgeConfig config) {
        BridgeConfig cfg = Objects.requireNonNull(config, "config");
        String symbol = cfg.symbol();
        Instant startedAt = clock.instant();
        Instant deadline = startedAt.plus(cfg.startupTimeout());
        Duration window = BRIDGE_WINDOW;
        Instant nextFromInclusive = cfg.parquetAnchorTsUtc().plusMillis(1L);
        Instant lastBridgedTickTs = null;
        int latestBarCount = 0;
        Long lastClientTickSeq = null;

        registry.markBridging(symbol, startedAt);
        try {
            while (true) {
                Instant requestedToInclusive = nextWindowEnd(nextFromInclusive, window, clock.instant());
                List<RuntimeTick> ticks = historyPort.getTicks(symbol, nextFromInclusive, requestedToInclusive).stream()
                        .sorted(Comparator.comparing(RuntimeTick::timestamp))
                        .toList();
                if (!ticks.isEmpty()) {
                    TickBatchResponsePayload batchResponse = predictionClient.tickBatch(new TickBatchRequestPayload(
                            symbol,
                            toPayloads(symbol, cfg.runId(), ticks),
                            cfg.runId()
                    ));
                    latestBarCount = batchResponse.barCount();
                    lastClientTickSeq = batchResponse.lastClientTickSeq();
                    lastBridgedTickTs = ticks.getLast().timestamp();
                    registry.recordBridgeProgress(symbol, requestedToInclusive, lastBridgedTickTs);
                }

                FeedBridgeStatus feedStatus = feedStatus(symbol, clock.instant(), cfg.freshnessThreshold());
                if (feedStatus.lastTickTsUtc() != null) {
                    registry.recordBridgeProgress(symbol, requestedToInclusive, feedStatus.lastTickTsUtc());
                }
                if (latestBarCount >= cfg.warmupBarCountThreshold() && feedStatus.fresh()) {
                    if (lastBridgedTickTs != null) {
                        registry.markBridgeComplete(symbol, lastBridgedTickTs);
                    }
                    registry.markReady(symbol, clock.instant(), latestBarCount, feedStatus.lastTickTsUtc());
                    return new BridgeResult(true, latestBarCount, feedStatus.lastTickTsUtc(), feedStatus.lastClientTickSeq());
                }
                if (!clock.instant().isBefore(deadline)) {
                    registry.markStartupTimeoutReached(symbol);
                    registry.markErrorPaused(
                            symbol,
                            clock.instant(),
                            "Broker bridge timed out before warmup/freshness requirements were satisfied"
                    );
                    return new BridgeResult(false, latestBarCount, lastBridgedTickTs, lastClientTickSeq);
                }

                nextFromInclusive = requestedToInclusive.plusMillis(1L);
            }
        } catch (Exception exc) {
            registry.markErrorPaused(symbol, clock.instant(), "Broker bridge failed: " + exc.getMessage());
            return new BridgeResult(false, latestBarCount, lastBridgedTickTs, lastClientTickSeq);
        }
    }

    private Instant nextWindowEnd(Instant nextFromInclusive, Duration window, Instant now) {
        Instant requestedToInclusive = nextFromInclusive.plus(window).minusMillis(1L);
        if (requestedToInclusive.isAfter(now)) {
            requestedToInclusive = now;
        }
        if (requestedToInclusive.isBefore(nextFromInclusive)) {
            return nextFromInclusive;
        }
        return requestedToInclusive;
    }

    private List<IncomingTickPayload> toPayloads(String symbol, String runId, List<RuntimeTick> ticks) {
        List<IncomingTickPayload> payloads = new ArrayList<>(ticks.size());
        long nextClientTickSeq = nextClientTickSeqBySymbol.getOrDefault(symbol, 1L);
        for (RuntimeTick tick : ticks) {
            payloads.add(new IncomingTickPayload(
                    symbol,
                    tick.timestamp(),
                    tick.bid(),
                    tick.ask(),
                    1.0,
                    nextClientTickSeq++,
                    runId
            ));
        }
        nextClientTickSeqBySymbol.put(symbol, nextClientTickSeq);
        return payloads;
    }

    private FeedBridgeStatus feedStatus(String symbol, Instant asOfUtc, Duration freshnessThreshold) {
        FeedStatusResponsePayload response = predictionClient.feedStatus();
        List<FeedStatusSymbolPayload> symbols = response.symbols() == null ? List.of() : response.symbols();
        FeedStatusSymbolPayload payload = symbols.stream()
                .filter(candidate -> normalizeSymbol(candidate.symbol()).equals(symbol))
                .findFirst()
                .orElse(null);
        if (payload == null || payload.lastTickTsUtc() == null) {
            return new FeedBridgeStatus(false, null, null);
        }
        long stalenessSeconds = Math.max(0L, Duration.between(payload.lastTickTsUtc(), asOfUtc).getSeconds());
        return new FeedBridgeStatus(
                stalenessSeconds <= freshnessThreshold.getSeconds(),
                payload.lastTickTsUtc(),
                payload.lastClientTickSeq()
        );
    }

    private static String normalizeSymbol(String rawSymbol) {
        String symbol = Objects.requireNonNull(rawSymbol, "symbol").trim().replace("/", "").toUpperCase();
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        return symbol;
    }

    public record BridgeConfig(
            String symbol,
            Instant parquetAnchorTsUtc,
            String runId,
            Duration bridgeWindow,
            Duration freshnessThreshold,
            Duration startupTimeout,
            int warmupBarCountThreshold
    ) {
        public BridgeConfig {
            symbol = normalizeSymbol(symbol);
            parquetAnchorTsUtc = Objects.requireNonNull(parquetAnchorTsUtc, "parquetAnchorTsUtc");
            runId = Objects.requireNonNullElse(runId, "").trim();
            bridgeWindow = Objects.requireNonNull(bridgeWindow, "bridgeWindow");
            freshnessThreshold = Objects.requireNonNull(freshnessThreshold, "freshnessThreshold");
            startupTimeout = Objects.requireNonNull(startupTimeout, "startupTimeout");
            if (!BRIDGE_WINDOW.equals(bridgeWindow)) {
                throw new IllegalArgumentException("bridgeWindow must be exactly PT60M");
            }
            if (freshnessThreshold.isNegative()) {
                throw new IllegalArgumentException("freshnessThreshold must be >= 0");
            }
            if (startupTimeout.isZero() || startupTimeout.isNegative()) {
                throw new IllegalArgumentException("startupTimeout must be > 0");
            }
            if (warmupBarCountThreshold <= 0) {
                throw new IllegalArgumentException("warmupBarCountThreshold must be > 0");
            }
        }
    }

    public record BridgeResult(
            boolean ready,
            int warmupBarCount100,
            Instant lastIngestedTickTsUtc,
            Long lastClientTickSeq
    ) {
    }

    private record FeedBridgeStatus(
            boolean fresh,
            Instant lastTickTsUtc,
            Long lastClientTickSeq
    ) {
    }
}
