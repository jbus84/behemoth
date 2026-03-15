package com.behemoth.jforex.core;

import java.time.Instant;
import java.util.Objects;

public record OrderEvent(
        OrderEventType type,
        String symbol,
        String orderLabel,
        String brokerOrderId,
        double openPrice,
        Instant fillTimeUtc,
        double closePrice,
        Instant closeTimeUtc,
        Double pnlPips,
        String detail
) {
    public OrderEvent {
        type = Objects.requireNonNull(type, "type");
        symbol = symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase();
        orderLabel = Objects.requireNonNull(orderLabel, "orderLabel").trim();
        brokerOrderId = Objects.requireNonNullElse(brokerOrderId, "").trim();
        detail = Objects.requireNonNullElse(detail, "");
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (orderLabel.isEmpty()) {
            throw new IllegalArgumentException("orderLabel must not be blank");
        }
    }
}
