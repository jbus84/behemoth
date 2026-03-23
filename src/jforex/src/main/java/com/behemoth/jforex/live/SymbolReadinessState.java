package com.behemoth.jforex.live;

public enum SymbolReadinessState {
    COLD,
    PARQUET_WARMING,
    BRIDGING,
    READY,
    STALE_PAUSED,
    ERROR_PAUSED
}
