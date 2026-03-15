package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.domain.PredictionDecision;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class OcoOrderPlannerTest {
    @Test
    void buildsPairedStopLimitPlanUsingCurrentCbotSemantics() {
        PredictionDecision decision = new PredictionDecision(
                "EURUSD",
                "oco|EURUSD|100|h6|state_a",
                2.0,
                1.2,
                100,
                6,
                10_000.0,
                "abc123"
        );

        OcoOrderPlan plan = OcoOrderPlanner.build(
                decision,
                1.1000,
                1.1002,
                0.0001,
                Instant.parse("2025-07-07T00:00:00Z")
        );

        assertThat(plan.groupLabel()).isEqualTo("OCO_EURUSD_T100_H6_TS20250707000000_RIDABC123_CIDB3B6C6DB72E3962C");
        assertThat(plan.buyLeg().side()).isEqualTo(OcoOrderPlan.Side.BUY);
        assertThat(plan.sellLeg().side()).isEqualTo(OcoOrderPlan.Side.SELL);
        assertThat(plan.buyLeg().label()).endsWith("_BUY");
        assertThat(plan.sellLeg().label()).endsWith("_SELL");
        assertThat(plan.buyLeg().comment()).contains("candidate_uid=oco|EURUSD|100|h6|state_a");
        assertThat(plan.sellLeg().comment()).contains("leg=SELL");
        assertThat(plan.buyLeg().triggerPrice()).isEqualTo(1.1004);
        assertThat(plan.sellLeg().triggerPrice()).isEqualTo(1.0998);
        assertThat(plan.stopLimitRangePips()).isEqualTo(1.2);
    }

    @Test
    void rejectsInvalidPriceInputs() {
        PredictionDecision decision = new PredictionDecision(
                "EURUSD",
                "candidate",
                2.0,
                1.2,
                100,
                6,
                10_000.0,
                ""
        );

        assertThatThrownBy(() -> OcoOrderPlanner.build(decision, 1.1002, 1.1000, 0.0001, Instant.now()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("invalid bid/ask");
    }

    @Test
    void keepsManualSiblingCancelAsSafetyFallbackWhenNativeOcoUnavailable() {
        assertThat(OcoOrderPlanner.requiresManualSiblingCancel(false)).isTrue();
        assertThat(OcoOrderPlanner.requiresManualSiblingCancel(true)).isTrue();
    }
}
