package com.behemoth.jforex.adapter;

/**
 * Concrete paired stop-limit entry plan for JForex execution.
 */
public record OcoOrderPlan(
        String groupLabel,
        EntryLeg buyLeg,
        EntryLeg sellLeg,
        double stopLimitRangePips
) {
    public record EntryLeg(
            String label,
            Side side,
            double triggerPrice,
            String comment
    ) {
    }

    public enum Side {
        BUY,
        SELL
    }
}
