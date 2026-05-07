package com.behemoth.jforex.core;

import java.util.Objects;

public record OrderResult(
        String orderId,
        String brokerPosId,
        String reservationId
) {
    public OrderResult {
        orderId = Objects.requireNonNullElse(orderId, "").trim();
        brokerPosId = Objects.requireNonNullElse(brokerPosId, "").trim();
        reservationId = Objects.requireNonNullElse(reservationId, "").trim();
    }
}
