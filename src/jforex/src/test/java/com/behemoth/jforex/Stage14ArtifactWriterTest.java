package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import java.nio.file.Files;
import java.nio.file.Path;
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
        writer.recordPredictCycle("GBPUSD", Instant.parse("2025-07-07T00:00:00Z"), 3, 1, 1, 0, List.of(), List.of(100));
        writer.recordOrderSubmitted("GBPUSD", "GROUP1", "GROUP1_BUY");
        writer.recordFill("GBPUSD", "GROUP1", "GROUP1_BUY");
        writer.recordTradeOpenSync("GBPUSD", "BUY-1");
        writer.recordTradeUpdateSync("GBPUSD", "BUY-1", "CLOSED");
        writer.markOperationalStep("GBPUSD", "market_order_submitted", true, "BM_scan-001_BUY");
        writer.writeReports(List.of("GBPUSD"));

        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_signal_parity_summary.csv")))
                .contains("jforex_signal_parity_pass")
                .contains("true");
        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_execution_parity_summary.csv")))
                .contains("jforex_execution_parity_pass")
                .contains("true");
        String lifecycleCsv = Files.readString(tempDir.resolve("GBPUSD_jforex_execution_lifecycle_summary.csv"));
        assertThat(lifecycleCsv)
                .contains("execution_lifecycle_pass")
                .contains("true");
        assertThat(Files.readString(tempDir.resolve("GBPUSD_jforex_operational_ready_summary.csv")))
                .contains("operational_ready_pass")
                .contains("true");
    }

    @Test
    void executionLifecycleFailsOnSubmitFailure() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir);
        writer.markOperationalStep("GBPUSD", "market_order_submitted", true, "BM_scan-001_BUY");
        writer.markOperationalStep("GBPUSD", "market_order_submit_failure", false, "connection timeout");
        writer.writeReports(List.of("GBPUSD"));

        String csv = Files.readString(tempDir.resolve("GBPUSD_jforex_execution_lifecycle_summary.csv"));
        assertThat(csv).contains("execution_lifecycle_pass").contains("false");
    }

    @Test
    void executionLifecycleFailsVacuouslyWhenNoActions() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir);
        writer.recordPredictCycle("GBPUSD", Instant.parse("2025-07-07T00:00:00Z"), 1, 0, 0, 0, List.of(), List.of(100));
        writer.writeReports(List.of("GBPUSD"));

        String csv = Files.readString(tempDir.resolve("GBPUSD_jforex_execution_lifecycle_summary.csv"));
        assertThat(csv).contains("execution_lifecycle_pass").contains("false");
    }

    @Test
    void executionLifecycleFailsWhenMarketOrderWasBlocked() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir);
        writer.markOperationalStep("GBPUSD", "market_order_blocked", false, "active_candidate_lifecycle");
        writer.writeReports(List.of("GBPUSD"));

        String csv = Files.readString(tempDir.resolve("GBPUSD_jforex_execution_lifecycle_summary.csv"));
        assertThat(csv)
                .contains("execution_lifecycle_pass")
                .contains("blocked_orders")
                .contains("\"1\"")
                .contains("false");
    }

    @Test
    void executionLifecycleFailsWhenBarrierCloseHasMissingPositionAnomaly() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir);
        writer.markOperationalStep("GBPUSD", "market_order_submitted", true, "BM_scan-001_BUY");
        writer.markOperationalStep("GBPUSD", "barrier_close_failure", false, "unknown broker_pos_id=missing-123");
        writer.writeReports(List.of("GBPUSD"));

        String csv = Files.readString(tempDir.resolve("GBPUSD_jforex_execution_lifecycle_summary.csv"));
        assertThat(csv)
                .contains("execution_lifecycle_pass")
                .contains("close_anomalies")
                .contains("\"1\"")
                .contains("false");
    }

    @Test
    void supportsAlternateArtifactPrefixesForLocalSurrogateRuns() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "local_jforex");
        writer.markOperationalStep("GBPUSD", "strategy_started", true, "ok");
        writer.markOperationalStep("GBPUSD", "subscribed", true, "ok");
        writer.markOperationalStep("GBPUSD", "feed_status", true, "ok");
        writer.markOperationalStep("GBPUSD", "account_snapshot", true, "ok");
        writer.recordPredictCycle("GBPUSD", Instant.parse("2025-07-07T00:00:00Z"), 1, 1, 1, 0, List.of(), List.of(100));
        writer.writeReports(List.of("GBPUSD"));

        assertThat(tempDir.resolve("GBPUSD_local_jforex_signal_parity_summary.csv")).exists();
        assertThat(Files.readString(tempDir.resolve("GBPUSD_local_jforex_operational_ready_summary.csv")))
                .contains("true");
    }

    @Test
    void recordPredictCycle_writesReplayCloseTimestamp() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "local_jforex");
        writer.recordPredictCycle("EURUSD", Instant.parse("2026-02-07T12:00:00Z"), 2, 1, 1, 0, List.of(), List.of(100));
        writer.writeReports(List.of("EURUSD"));

        String content = Files.readString(tempDir.resolve("EURUSD_local_jforex_runtime_events.csv"));
        assertThat(content).contains("close_ts=2026-02-07T12:00:00Z");
    }

    @Test
    void recordPredictCycle_writesExecutableAndBlockedDiagnostics() throws Exception {
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "local_jforex");
        writer.recordPredictCycle(
                "EURUSD",
                Instant.parse("2026-02-07T12:00:00Z"),
                3,
                3,
                1,
                2,
                List.of("entries_paused", "active_candidate_lifecycle"),
                List.of(100)
        );
        writer.writeReports(List.of("EURUSD"));

        String content = Files.readString(tempDir.resolve("EURUSD_local_jforex_runtime_events.csv"));
        assertThat(content).contains("prediction_count=3");
        assertThat(content).contains("selected_count=3");
        assertThat(content).contains("executable_selected_count=1");
        assertThat(content).contains("blocked_count=2");
        assertThat(content).contains("blocked_reasons=entries_paused,active_candidate_lifecycle");
        assertThat(content).contains("close_ts=2026-02-07T12:00:00Z");
    }

    @Test
    void recordTradeOutcome_writesEnrichedExecutionEvent() throws Exception {
        Path tmp = Files.createTempDirectory("s14test");
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tmp, "local_jforex");
        writer.recordTradeOutcome("EURUSD", "OCO_EURUSD_GROUP1", "uid_a", "BUY", 1.08500, 1.08538, 3.8);
        writer.writeReports(List.of("EURUSD"));

        Path events = tmp.resolve("EURUSD_local_jforex_runtime_events.csv");
        String content = Files.readString(events);
        assertThat(content).contains("trade_outcome");
        assertThat(content).contains("candidate_uid=uid_a");
        assertThat(content).contains("side=BUY");
        assertThat(content).contains("pnl_pips=3.8");
    }
}
