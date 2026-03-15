package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.domain.PredictionDecision;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.state.ExecutionStateStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExecutionStateStoreTest {
    @TempDir
    java.nio.file.Path tempDir;

    @Test
    void fillMarksSiblingForCancelAndDeduplicatesTradeSyncFlags() {
        ObjectMapper mapper = new PythonPredictionClient(HttpClient.newHttpClient(), URI.create("http://127.0.0.1:8000"))
                .objectMapper();
        ExecutionStateStore store = new ExecutionStateStore(tempDir.resolve("state.json"), mapper);
        PredictionDecision decision = new PredictionDecision(
                "GBPUSD",
                "oco|GBPUSD|100|h6|state_a",
                2.0,
                1.2,
                100,
                6,
                10_000.0,
                "res1"
        );
        OcoOrderPlan plan = OcoOrderPlanner.build(
                decision,
                1.2500,
                1.2502,
                0.0001,
                Instant.parse("2025-07-07T00:00:00Z")
        );
        store.registerPlannedGroup("GBPUSD", decision, plan, "run-1", Instant.parse("2025-07-07T00:00:00Z"), false);
        store.markSubmitAccepted(plan.buyLeg().label(), "BUY-1", 0.01);
        store.markSubmitAccepted(plan.sellLeg().label(), "SELL-1", 0.01);

        ExecutionStateStore.FillAction fill = store.markFilled(
                plan.buyLeg().label(),
                "BUY-1",
                1.2504,
                Instant.parse("2025-07-07T00:00:10Z")
        );

        assertThat(fill.shouldNotifyTradeOpen()).isTrue();
        assertThat(fill.siblingLabelToCancel()).isEqualTo(plan.sellLeg().label());
        assertThat(store.markTradeTouchSynced(plan.buyLeg().label())).isTrue();
        assertThat(store.markTradeTouchSynced(plan.buyLeg().label())).isFalse();
        assertThat(store.markTradeUpdateSynced(plan.buyLeg().label())).isTrue();
        assertThat(store.markTradeUpdateSynced(plan.buyLeg().label())).isFalse();
    }
}
