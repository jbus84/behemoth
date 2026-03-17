package com.behemoth.jforex.runtime.dto;

import java.util.List;
import java.util.Map;

public record PredictRequestPayload(
        String symbol,
        Boolean riskEnabledOverride,
        Double requestedVolumeUnits,
        List<Integer> completedBarTicks,
        String runId,
        Map<Integer, Long> barOrdinals
) {
}
