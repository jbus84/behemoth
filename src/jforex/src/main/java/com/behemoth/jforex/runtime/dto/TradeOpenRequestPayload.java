package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record TradeOpenRequestPayload(
        String symbol,
        String candidateUid,
        String brokerPosId,
        String side,
        double entryPrice,
        Instant entryTs,
        int horizon,
        String reservationId,
        String runId
) {
}
