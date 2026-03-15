package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.adapter.OcoOrderPlanner;
import com.behemoth.jforex.domain.PredictionDecision;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.state.OcoGroupState;
import java.nio.file.Files;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class Stage14ArtifactWriterTest {
    @TempDir
    java.nio.file.Path tempDir;

    @Test
    void writesExpectedStage14SummaryFiles() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir);
        writer.markOperationalStep("GBPUSD", "strategy_started", true, "ok");
        writer.markOperationalStep("GBPUSD", "subscribed", true, "ok");
        writer.markOperationalStep("GBPUSD", "feed_status", true, "ok");
        writer.markOperationalStep("GBPUSD", "account_snapshot", true, "ok");
        writer.recordPredictCycle("GBPUSD", 3, 1, 0, List.of(100));
        writer.recordOrderSubmitted("GBPUSD", "GROUP1", "GROUP1_BUY");
        writer.recordFill("GBPUSD", "GROUP1", "GROUP1_BUY");
        writer.recordTradeOpenSync("GBPUSD", "BUY-1");
        writer.recordTradeTouchSync("GBPUSD", "BUY-1");
        writer.recordTradeUpdateSync("GBPUSD", "BUY-1", "CLOSED");
        PredictionDecision decision = new PredictionDecision(
                "GBPUSD",
                "oco|GBPUSD|100|h6|state_a",
                2.0,
                1.2,
                100,
                6,
                10000.0,
                "rid1"
        );
        OcoOrderPlan plan = OcoOrderPlanner.build(
                decision,
                1.2500,
                1.2502,
                0.0001,
                Instant.parse("2025-07-07T00:00:00Z")
        );
        OcoGroupState group = OcoGroupState.from(
                "GBPUSD",
                decision,
                plan,
                "run-1",
                Instant.parse("2025-07-07T00:00:00Z"),
                false
        );
        writer.writeReports(List.of("GBPUSD"), List.of(group));

        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_signal_parity_summary.csv")))
                .contains("jforex_signal_parity_pass")
                .contains("true");
        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_execution_parity_summary.csv")))
                .contains("jforex_execution_parity_pass")
                .contains("true");
        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_oco_lifecycle_summary.csv")))
                .contains("oco_lifecycle_pass")
                .contains("true");
        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_operational_ready_summary.csv")))
                .contains("operational_ready_pass")
                .contains("true");
    }

    @Test
    void supportsAlternateArtifactPrefixesForLocalSurrogateRuns() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "local_jforex");
        writer.markOperationalStep("GBPUSD", "strategy_started", true, "ok");
        writer.markOperationalStep("GBPUSD", "subscribed", true, "ok");
        writer.markOperationalStep("GBPUSD", "feed_status", true, "ok");
        writer.markOperationalStep("GBPUSD", "account_snapshot", true, "ok");
        writer.recordPredictCycle("GBPUSD", 1, 1, 0, List.of(100));
        writer.writeReports(List.of("GBPUSD"), List.of());

        assertThat(tempDir.resolve("GBPUSD_local_jforex_signal_parity_summary.csv")).exists();
        assertThat(Files.readString(tempDir.resolve("GBPUSD_local_jforex_operational_ready_summary.csv")))
                .contains("true");
    }
}
