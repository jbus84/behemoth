package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record FeedStatusSymbolPayload(
        String symbol,
        int totalReceived,
        int totalAccepted,
        int totalDropped,
        int totalBatches,
        int duplicateTimestamps,
        int monotonicViolations,
        int duplicateClientTickSeq,
        int clientSeqViolations,
        long symbolTickSeq,
        Long lastClientTickSeq,
        Instant lastTickTsUtc,
        Instant lastIngestUtc,
        String lastDropReason
) {
}
