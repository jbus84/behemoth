package com.behemoth.jforex.runtime.dto;

public record TradeTouchRequestPayload(
        String symbol,
        String brokerPosId,
        String runId
) {
}
