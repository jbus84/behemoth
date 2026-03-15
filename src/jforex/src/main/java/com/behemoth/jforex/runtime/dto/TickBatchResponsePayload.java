package com.behemoth.jforex.runtime.dto;

import java.time.Instant;
import java.util.List;

public record TickBatchResponsePayload(
        boolean ok,
        String symbol,
        int ticksReceived,
        int acceptedCount,
        int droppedCount,
        boolean barCompleted,
        List<Integer> completedBarTicks,
        long symbolTickSeq,
        Instant lastTickTsUtc,
        Long lastClientTickSeq,
        int barCount
) {
}
