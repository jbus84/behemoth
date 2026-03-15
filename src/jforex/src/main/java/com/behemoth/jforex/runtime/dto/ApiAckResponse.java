package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record ApiAckResponse(
        Boolean ok,
        String status,
        String symbol,
        Instant snapshotTs,
        String internalTradeId
) {
}
