package com.behemoth.jforex.core;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderBookingServiceTest {

    private static JForexMetrics noOpMetrics() {
        return JForexMetrics.start(new JForexSessionConfig(
                URI.create("http://localhost:8080"),
                URI.create("http://localhost:8081"),
                "user", "pass", "",
                List.of("EURUSD"),
                Instant.parse("2025-01-01T00:00:00Z"),
                Instant.parse("2025-01-02T00:00:00Z"),
                Path.of("/tmp"), "run-1",
                false, 10_000.0, 1, 900L,
                false, 60,
                false, "", 0
        ));
    }

    static class RecordingExecutionPort implements ExecutionPort {
        OrderSubmissionRequest lastMarketRequest;
        String lastCloseSymbol;
        String lastCloseLabel;

        @Override
        public OrderHandle submitStopOrder(OrderRequest request) {
            return new OrderHandle(request.label(), "order-" + request.label());
        }

        @Override
        public OrderResult submitMarketOrder(OrderSubmissionRequest request) {
            lastMarketRequest = request;
            return new OrderResult("order-" + request.label(), "pos-" + request.label(), request.reservationId());
        }

        @Override
        public void cancelOrder(String symbol, String label) {}

        @Override
        public void closePosition(String symbol, String label) {
            lastCloseSymbol = symbol;
            lastCloseLabel = label;
        }
    }

    @Test
    void submitMarketOrder_delegatesToExecutionPort() throws Exception {
        Path tempDir = Files.createTempDirectory("obs-test");
        RecordingExecutionPort port = new RecordingExecutionPort();
        JForexMetrics metrics = noOpMetrics();
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
        OrderBookingService service = new OrderBookingService(port, metrics, writer);

        OrderIntent intent = new OrderIntent(
                "EURUSD", "scan-1", "BUY", 1.0,
                "cand-1", "res-1", 6, Instant.parse("2025-07-07T00:00:00Z")
        );
        OrderResult result = service.submitMarketOrder(intent);

        assertThat(result.orderId()).isEqualTo("order-BM_scan-1_BUY");
        assertThat(result.reservationId()).isEqualTo("res-1");
        assertThat(port.lastMarketRequest).isNotNull();
        assertThat(port.lastMarketRequest.symbol()).isEqualTo("EURUSD");
        assertThat(port.lastMarketRequest.label()).isEqualTo("BM_scan-1_BUY");
        assertThat(port.lastMarketRequest.scanId()).isEqualTo("scan-1");
        assertThat(port.lastMarketRequest.side()).isEqualTo("BUY");
        assertThat(port.lastMarketRequest.amountMillions()).isEqualTo(1.0);
        assertThat(port.lastMarketRequest.candidateUid()).isEqualTo("cand-1");
        assertThat(port.lastMarketRequest.reservationId()).isEqualTo("res-1");
        assertThat(port.lastMarketRequest.horizon()).isEqualTo(6);

        // pendingFills must be populated for lifecycle handler
        assertThat(service.pendingFills()).containsKey("BM_scan-1_BUY");
        assertThat(service.orderLabelForScan("scan-1")).isEqualTo("BM_scan-1_BUY");
    }

    @Test
    void submitMarketOrder_cleansUpOnFailure() throws Exception {
        Path tempDir = Files.createTempDirectory("obs-test");
        ExecutionPort failingPort = new ExecutionPort() {
            @Override public OrderHandle submitStopOrder(OrderRequest request) { return null; }
            @Override public OrderResult submitMarketOrder(OrderSubmissionRequest request) {
                throw new RuntimeException("broker down");
            }
            @Override public void cancelOrder(String symbol, String label) {}
            @Override public void closePosition(String symbol, String label) {}
        };
        JForexMetrics metrics = noOpMetrics();
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
        OrderBookingService service = new OrderBookingService(failingPort, metrics, writer);

        OrderIntent intent = new OrderIntent(
                "EURUSD", "scan-fail", "SELL", 0.5,
                "cand-1", "res-1", 3, Instant.now()
        );
        OrderResult result = service.submitMarketOrder(intent);

        assertThat(result.orderId()).isEmpty();
        assertThat(service.pendingFills()).isEmpty();
        assertThat(service.orderLabelForScan("scan-fail")).isNull();
    }

    @Test
    void closePositionByScanId_delegatesToExecutionPort() throws Exception {
        Path tempDir = Files.createTempDirectory("obs-test");
        RecordingExecutionPort port = new RecordingExecutionPort();
        JForexMetrics metrics = noOpMetrics();
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
        OrderBookingService service = new OrderBookingService(port, metrics, writer);

        // Prime the scan-to-label mapping via submit
        OrderIntent intent = new OrderIntent(
                "EURUSD", "scan-close", "BUY", 1.0,
                "cand-1", "res-1", 6, Instant.now()
        );
        service.submitMarketOrder(intent);

        service.closePositionByScanId("EURUSD", "scan-close", Instant.now());

        assertThat(port.lastCloseSymbol).isEqualTo("EURUSD");
        assertThat(port.lastCloseLabel).isEqualTo("BM_scan-close_BUY");
        assertThat(service.orderLabelForScan("scan-close")).isNull();
    }

    @Test
    void closePositionByScanId_skipsWhenNoLabel() throws Exception {
        Path tempDir = Files.createTempDirectory("obs-test");
        RecordingExecutionPort port = new RecordingExecutionPort();
        JForexMetrics metrics = noOpMetrics();
        Stage14ArtifactWriter writer = new Stage14ArtifactWriter(tempDir, "test");
        OrderBookingService service = new OrderBookingService(port, metrics, writer);

        service.closePositionByScanId("EURUSD", "unknown-scan", Instant.now());

        assertThat(port.lastCloseLabel).isNull();
    }
}
