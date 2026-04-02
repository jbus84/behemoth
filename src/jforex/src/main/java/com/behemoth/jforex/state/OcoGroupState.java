package com.behemoth.jforex.state;

import java.time.Instant;

/**
 * Persisted local runtime state for one paired OCO submission.
 */
public final class OcoGroupState {
    public String groupLabel;
    public String symbol;
    public String candidateUid;
    public String reservationId;
    public int barTicks;
    public int horizon;
    public String runId;
    public long placedAtEpochMs;
    public boolean nativeOcoRequested;
    public boolean lifecycleViolation;
    public String lastError;
    public OcoLegState buyLeg;
    public OcoLegState sellLeg;

    public OcoGroupState() {
    }

    public OcoLegState legForLabel(String label) {
        if (buyLeg != null && buyLeg.label != null && buyLeg.label.equals(label)) {
            return buyLeg;
        }
        if (sellLeg != null && sellLeg.label != null && sellLeg.label.equals(label)) {
            return sellLeg;
        }
        return null;
    }

    public OcoLegState siblingOf(String label) {
        if (buyLeg != null && buyLeg.label != null && buyLeg.label.equals(label)) {
            return sellLeg;
        }
        if (sellLeg != null && sellLeg.label != null && sellLeg.label.equals(label)) {
            return buyLeg;
        }
        return null;
    }

    public boolean isActive() {
        return (buyLeg != null && buyLeg.isActive()) || (sellLeg != null && sellLeg.isActive());
    }

    public static final class OcoLegState {
        public String label;
        public String side;
        public String comment;
        public double triggerPrice;
        public String orderId;
        public String status;
        public boolean cancelRequested;
        public boolean openNotified;
        public boolean touchNotified;
        public boolean updateNotified;
        public double amountMillions;
        public Double fillPrice;
        public Long fillEpochMs;
        public Double closePrice;
        public Long closeEpochMs;
        public Double pnlPips;
        public String lastMessage;

        public OcoLegState() {
        }

        public boolean isActive() {
            return switch (String.valueOf(status)) {
                case "PLANNED", "SUBMIT_OK", "FILLED", "CANCEL_REQUESTED" -> true;
                default -> false;
            };
        }

        public boolean wasFilled() {
            return fillEpochMs != null || "FILLED".equals(status) || "CLOSED".equals(status);
        }
    }
}
