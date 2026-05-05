package com.behemoth.jforex.worker;

import java.time.Instant;
import java.util.Objects;

/**
 * Immutable carrier of a single tick, enqueued by the strategy thread
 * and consumed by a per-symbol worker thread.
 *
 * <p>{@code receiveTimeNs} captures {@link System#nanoTime()} at the moment
 * of enqueue so the worker can measure queue-age (back-pressure) per tick.
 */
public record TickEvent(long epochMs, double bid, double ask, long receiveTimeNs) {

    public TickEvent {
        if (bid <= 0) {
            throw new IllegalArgumentException("bid must be > 0, was: " + bid);
        }
        if (ask <= 0) {
            throw new IllegalArgumentException("ask must be > 0, was: " + ask);
        }
        if (ask < bid) {
            throw new IllegalArgumentException(
                "ask (" + ask + ") must be >= bid (" + bid + ")"
            );
        }
    }

    /**
     * Returns the tick wall-clock time as an {@link Instant}.
     */
    public Instant timestamp() {
        return Instant.ofEpochMilli(epochMs);
    }
}
