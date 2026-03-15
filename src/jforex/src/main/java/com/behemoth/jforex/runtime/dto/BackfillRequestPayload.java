package com.behemoth.jforex.runtime.dto;

import java.util.List;

public record BackfillRequestPayload(
        String symbol,
        int barTicks,
        List<IncomingTickPayload> ticks,
        String runId
) {
}
