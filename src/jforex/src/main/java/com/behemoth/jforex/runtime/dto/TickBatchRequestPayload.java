package com.behemoth.jforex.runtime.dto;

import java.util.List;

public record TickBatchRequestPayload(
        String symbol,
        List<IncomingTickPayload> ticks,
        String runId
) {
}
