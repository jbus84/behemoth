package com.behemoth.jforex.live;

import com.behemoth.jforex.core.RuntimeTick;
import com.dukascopy.api.IHistory;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class JForexBrokerHistoryPort implements BrokerHistoryPort {
    private final IHistory history;

    public JForexBrokerHistoryPort(IHistory history) {
        this.history = Objects.requireNonNull(history, "history");
    }

    @Override
    public List<RuntimeTick> getTicks(String symbol, Instant fromInclusive, Instant toInclusive) throws Exception {
        String normalized = normalizeSymbol(symbol);
        if (toInclusive.isBefore(fromInclusive)) {
            return List.of();
        }
        Instrument instrument = Instrument.valueOf(normalized);
        List<ITick> ticks = history.getTicks(instrument, fromInclusive.toEpochMilli(), toInclusive.toEpochMilli());
        return ticks.stream()
                .map(tick -> new RuntimeTick(
                        normalized,
                        Instant.ofEpochMilli(tick.getTime()),
                        tick.getBid(),
                        tick.getAsk()
                ))
                .sorted(Comparator.comparing(RuntimeTick::timestamp))
                .toList();
    }

    private static String normalizeSymbol(String rawSymbol) {
        return Objects.requireNonNull(rawSymbol, "symbol").trim().replace("/", "").toUpperCase();
    }
}
