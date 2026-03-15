package com.behemoth.jforex.runtime.dto;

import java.time.Instant;
import java.util.List;

public record FeedStatusResponsePayload(
        Instant asOfUtc,
        String governanceMode,
        boolean recordRawTicks,
        List<FeedStatusSymbolPayload> symbols
) {
}
