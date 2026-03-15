package com.behemoth.jforex.runtime.dto;

public record ActiveTradePayload(
        String brokerPosId,
        int entryBarId,
        int horizon,
        Integer touchBarId
) {
}
