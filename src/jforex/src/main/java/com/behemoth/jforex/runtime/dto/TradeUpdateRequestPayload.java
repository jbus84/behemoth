package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record TradeUpdateRequestPayload(
        String symbol,
        String brokerPosId,
        String status,
        Double exitPrice,
        Instant exitTs,
        Double pnlPips,
        String runId,
        String closeReason,
        Double commissionCcy
) {
}
