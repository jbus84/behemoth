package com.behemoth.jforex.observability;

import com.behemoth.jforex.live.SymbolReadinessState;

public interface LiveReadinessMetrics {
    void setReadinessState(String symbol, SymbolReadinessState state);

    void setEntriesAllowed(String symbol, boolean allowed);

    void setTickStalenessSeconds(String symbol, long stalenessSeconds);

    void recordReadinessTransition(String symbol, SymbolReadinessState fromState, SymbolReadinessState toState);

    void recordReadinessTimeout(String symbol);
}
