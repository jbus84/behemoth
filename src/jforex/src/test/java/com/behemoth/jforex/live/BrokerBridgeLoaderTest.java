package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;

class BrokerBridgeLoaderTest {
    @Test
    void bridgeLoaderTimesOutWhenFreshnessNeverRecovers() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(List.of(), () -> clock.advance(Duration.ofMinutes(10)));
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T10:00:00Z"));
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T10:00:00Z"));
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:00:00Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289
            ));

            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").startupTimeoutReached()).isTrue();
            assertThat(historyPort.requests()).hasSize(2);
            assertThat(server.getRequestCount()).isEqualTo(2);
            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");
            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");
        }
    }

    @Test
    void bridgeTicksContinueClientTickSequenceAfterBackfill() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:20Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(List.of(List.of(
                new RuntimeTick("EURUSD", Instant.parse("2026-03-22T11:59:58Z"), 1.0850, 1.0852),
                new RuntimeTick("EURUSD", Instant.parse("2026-03-22T11:59:59Z"), 1.0851, 1.0853),
                new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:00:00Z"), 1.0852, 1.0854)
        )), () -> {
        });
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {
                              "ok": true,
                              "symbol": "EURUSD",
                              "ticks_received": 3,
                              "accepted_count": 3,
                              "dropped_count": 0,
                              "bar_completed": false,
                              "completed_bar_ticks": [],
                              "symbol_tick_seq": 30078,
                              "last_tick_ts_utc": "2026-03-22T12:00:00Z",
                              "last_client_tick_seq": 30078,
                              "bar_count": 289
                            }
                            """));
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T12:00:00Z"));
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);
            loader.seedClientTickSeq("EURUSD", 30_075L);

            loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:57Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289
            ));

            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(registry.snapshot("EURUSD").warmupBarCount100()).isEqualTo(289);
            assertThat(registry.snapshot("EURUSD").bridgeEndTsUtc()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));

            RecordedRequest batchRequest = server.takeRequest();
            assertThat(batchRequest.getPath()).isEqualTo("/ticks/batch");
            TickBatchRequestPayload payload = predictionClient.objectMapper()
                    .readValue(batchRequest.getBody().readUtf8(), TickBatchRequestPayload.class);
            assertThat(payload.ticks())
                    .extracting(tick -> tick.clientTickSeq())
                    .containsExactly(30_076L, 30_077L, 30_078L);
            assertThat(payload.ticks())
                    .extracting(tick -> tick.tickVolume())
                    .containsExactly(1.0, 1.0, 1.0);
            assertThat(payload.ticks())
                    .extracting(tick -> tick.runId())
                    .containsExactly("run-1", "run-1", "run-1");

            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");
        }
    }

    private static MockResponse feedStatusResponse(String symbol, String lastTickTsUtc) {
        return new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""
                        {
                          "as_of_utc": "2026-03-22T12:00:00Z",
                          "governance_mode": "live",
                          "record_raw_ticks": true,
                          "symbols": [
                            {
                              "symbol": "%s",
                              "total_received": 100,
                              "total_accepted": 100,
                              "total_dropped": 0,
                              "total_batches": 1,
                              "duplicate_timestamps": 0,
                              "monotonic_violations": 0,
                              "duplicate_client_tick_seq": 0,
                              "client_seq_violations": 0,
                              "symbol_tick_seq": 100,
                              "last_client_tick_seq": 100,
                              "last_tick_ts_utc": "%s",
                              "last_ingest_utc": "%s",
                              "last_drop_reason": ""
                            }
                          ]
                        }
                        """.formatted(symbol, lastTickTsUtc, lastTickTsUtc));
    }

    private record WindowRequest(Instant fromInclusive, Instant toInclusive) {
    }

    private static final class FakeBrokerHistoryPort implements BrokerHistoryPort {
        private final Deque<List<RuntimeTick>> responses;
        private final List<WindowRequest> requests = new ArrayList<>();
        private final Runnable onCall;

        private FakeBrokerHistoryPort(List<List<RuntimeTick>> responses, Runnable onCall) {
            this.responses = new ArrayDeque<>(responses);
            this.onCall = onCall;
        }

        @Override
        public List<RuntimeTick> getTicks(String symbol, Instant fromInclusive, Instant toInclusive) {
            requests.add(new WindowRequest(fromInclusive, toInclusive));
            onCall.run();
            List<RuntimeTick> response = responses.pollFirst();
            return response == null ? List.of() : response;
        }

        private List<WindowRequest> requests() {
            return List.copyOf(requests);
        }
    }

    private static final class MutableClock extends Clock {
        private Instant instant;
        private final ZoneId zoneId;

        private MutableClock(Instant instant, ZoneId zoneId) {
            this.instant = instant;
            this.zoneId = zoneId;
        }

        @Override
        public ZoneId getZone() {
            return zoneId;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return new MutableClock(instant, zone);
        }

        @Override
        public Instant instant() {
            return instant;
        }

        private void advance(Duration duration) {
            instant = instant.plus(duration);
        }
    }
}
