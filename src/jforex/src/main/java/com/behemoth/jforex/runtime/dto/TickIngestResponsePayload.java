package com.behemoth.jforex.runtime.dto;

import java.time.Instant;
import java.util.List;

public record TickIngestResponsePayload(
        boolean ok,
        String symbol,
        boolean tickAccepted,
        String dropReason,
        long symbolTickSeq,
        Instant lastTickTsUtc,
        Long lastClientTickSeq,
        boolean barCompleted,
        List<Integer> completedBarTicks,
        int barCount
) {
}
