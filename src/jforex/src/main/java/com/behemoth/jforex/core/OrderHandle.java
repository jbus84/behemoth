package com.behemoth.jforex.core;

import java.util.Objects;

public record OrderHandle(
        String label,
        String brokerOrderId
) {
    public OrderHandle {
        label = Objects.requireNonNull(label, "label").trim();
        brokerOrderId = Objects.requireNonNullElse(brokerOrderId, "").trim();
        if (label.isEmpty()) {
            throw new IllegalArgumentException("label must not be blank");
        }
    }
}
