package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record IncomingTickPayload(
        String symbol,
        Instant timestamp,
        double bid,
        double ask,
        double tickVolume,
        Long clientTickSeq,
        String runId
) {
}
