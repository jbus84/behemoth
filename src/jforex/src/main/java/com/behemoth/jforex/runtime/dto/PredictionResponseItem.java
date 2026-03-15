package com.behemoth.jforex.runtime.dto;

import com.behemoth.jforex.domain.PredictionDecision;
import java.time.Instant;

public record PredictionResponseItem(
        String symbol,
        Instant closeTs,
        String candidateUid,
        double predProb,
        double thresholdExec,
        int selectedExec,
        int barTicks,
        int horizon,
        double barrierPips,
        double capPips,
        boolean riskBlocked,
        String riskBlockReason,
        String riskReservationId
) {
    public boolean isSelected() {
        return selectedExec == 1;
    }

    public boolean isExecutable(boolean riskEnabled) {
        if (!isSelected()) {
            return false;
        }
        return !riskEnabled || !riskBlocked;
    }

    public PredictionDecision toDecision(double requestedVolumeUnits) {
        return new PredictionDecision(
                symbol,
                candidateUid,
                barrierPips,
                capPips,
                barTicks,
                horizon,
                requestedVolumeUnits,
                riskReservationId == null ? "" : riskReservationId
        );
    }
}
