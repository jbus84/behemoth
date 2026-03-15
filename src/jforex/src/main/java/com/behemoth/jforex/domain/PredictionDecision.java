package com.behemoth.jforex.domain;

import java.util.Objects;

/**
 * Broker-side execution instruction emitted by the Python decision engine.
 */
public record PredictionDecision(
        String symbol,
        String candidateUid,
        double barrierPips,
        double capPips,
        int barTicks,
        int horizon,
        double requestedVolumeUnits,
        String reservationId
) {
    public PredictionDecision {
        symbol = Objects.requireNonNull(symbol, "symbol").trim().toUpperCase();
        candidateUid = Objects.requireNonNull(candidateUid, "candidateUid").trim();
        reservationId = reservationId == null ? "" : reservationId.trim();
        if (symbol.isEmpty()) {
            throw new IllegalArgumentException("symbol must not be blank");
        }
        if (candidateUid.isEmpty()) {
            throw new IllegalArgumentException("candidateUid must not be blank");
        }
        if (barrierPips <= 0.0) {
            throw new IllegalArgumentException("barrierPips must be > 0");
        }
        if (capPips <= 0.0) {
            throw new IllegalArgumentException("capPips must be > 0");
        }
        if (barTicks <= 0) {
            throw new IllegalArgumentException("barTicks must be > 0");
        }
        if (horizon <= 0) {
            throw new IllegalArgumentException("horizon must be > 0");
        }
        if (requestedVolumeUnits <= 0.0) {
            throw new IllegalArgumentException("requestedVolumeUnits must be > 0");
        }
    }
}
