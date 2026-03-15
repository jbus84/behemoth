package com.behemoth.jforex.runtime.dto;

import java.util.List;

public record PredictRequestPayload(
        String symbol,
        Boolean riskEnabledOverride,
        Double requestedVolumeUnits,
        List<Integer> completedBarTicks,
        String runId
) {
}
