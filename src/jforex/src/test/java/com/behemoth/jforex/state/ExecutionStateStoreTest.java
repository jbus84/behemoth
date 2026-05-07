package com.behemoth.jforex.state;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExecutionStateStoreTest {
    @TempDir
    Path tempDir;

    @Test
    void fillAndCloseActionsExposeLifecycleTransitions() throws Exception {
        Path statePath = tempDir.resolve("execution-state.json");
        ObjectMapper mapper = new ObjectMapper()
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        statePath.toFile().getParentFile().mkdirs();
        statePath.toFile().createNewFile();

        OcoGroupState group = new OcoGroupState();
        group.groupLabel = "BM_scan";
        group.symbol = "EURUSD";
        group.buyLeg = new OcoGroupState.OcoLegState();
        group.buyLeg.label = "BM_scan_BUY";
        group.buyLeg.status = "SUBMIT_OK";
        group.sellLeg = new OcoGroupState.OcoLegState();
        group.sellLeg.label = "BM_scan_SELL";
        group.sellLeg.status = "SUBMIT_OK";
        mapper.writeValue(statePath.toFile(), java.util.List.of(group));

        ExecutionStateStore store = new ExecutionStateStore(statePath, mapper);
        ExecutionStateStore.FillAction fill = store.markFilled(
                "BM_scan_BUY",
                "order-1",
                1.1,
                Instant.parse("2026-03-06T12:00:00Z")
        );
        ExecutionStateStore.CloseAction close = store.markClosed(
                "BM_scan_BUY",
                1.101,
                Instant.parse("2026-03-06T12:05:00Z"),
                1.0
        );

        assertThat(fill.transition().fromStatus()).isEqualTo("SUBMIT_OK");
        assertThat(fill.transition().toStatus()).isEqualTo("FILLED");
        assertThat(fill.siblingLabelToCancel()).isEqualTo("BM_scan_SELL");
        assertThat(close.transition().fromStatus()).isEqualTo("FILLED");
        assertThat(close.transition().toStatus()).isEqualTo("CLOSED");
    }
}
