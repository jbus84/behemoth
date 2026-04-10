package com.behemoth.jforex.live;

import com.behemoth.jforex.core.RuntimeTick;
import java.time.Instant;
import java.util.List;

public interface BrokerHistoryPort {
    List<RuntimeTick> getTicks(String symbol, Instant fromInclusive, Instant toInclusive) throws Exception;

    default Instant getLastTickTimestamp(String symbol) throws Exception {
        return null;
    }
}
