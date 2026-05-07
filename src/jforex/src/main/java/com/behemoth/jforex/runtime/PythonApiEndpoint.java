package com.behemoth.jforex.runtime;

import java.time.Duration;

public enum PythonApiEndpoint {
    ACCOUNT_SNAPSHOT("POST", "/risk/account/snapshot", TimeoutProfile.REGULAR),
    BACKFILL("POST", "/backfill", TimeoutProfile.REGULAR),
    TICK_BATCH("POST", "/ticks/batch", TimeoutProfile.TICK_BATCH),
    TICK("POST", "/ticks", TimeoutProfile.TICK_BATCH),
    PREDICT("POST", "/predict", TimeoutProfile.REGULAR),
    TRADE_OPEN("POST", "/trades/open", TimeoutProfile.REGULAR),
    TRADE_TOUCH("POST", "/trades/touch", TimeoutProfile.REGULAR),
    TRADE_UPDATE("POST", "/trades/update", TimeoutProfile.REGULAR),
    FEED_STATUS("GET", "/runtime/feed/status", TimeoutProfile.REGULAR),
    ACTIVE_TRADES("GET", "/trades/active", TimeoutProfile.REGULAR);

    private final String method;
    private final String path;
    private final TimeoutProfile timeoutProfile;

    PythonApiEndpoint(String method, String path, TimeoutProfile timeoutProfile) {
        this.method = method;
        this.path = path;
        this.timeoutProfile = timeoutProfile;
    }

    public String method() {
        return method;
    }

    public String path() {
        return path;
    }

    public Duration timeout(Duration requestTimeout, Duration tickBatchTimeout) {
        return timeoutProfile == TimeoutProfile.TICK_BATCH ? tickBatchTimeout : requestTimeout;
    }

    private enum TimeoutProfile {
        REGULAR,
        TICK_BATCH
    }
}
