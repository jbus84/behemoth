package com.behemoth.jforex.runtime.dto;

import java.time.Instant;

public record AccountSnapshotRequestPayload(
        String symbol,
        double balance,
        double equity,
        Instant snapshotTs,
        String runId
) {
}
