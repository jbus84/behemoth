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
import okhttp3.mockwebserver.SocketPolicy;
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
                    289,
                    0
            ));

            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").startupTimeoutReached()).isTrue();
            assertThat(historyPort.requests()).hasSize(2);
            assertThat(historyPort.requests().get(0).fromInclusive()).isEqualTo(Instant.parse("2026-03-22T11:00:00.001Z"));
            assertThat(historyPort.requests().get(0).toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));
            assertThat(historyPort.requests().get(1).fromInclusive()).isEqualTo(Instant.parse("2026-03-22T11:00:00.001Z"));
            assertThat(historyPort.requests().get(1).toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));
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
                    289,
                    0
            ));

            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(registry.snapshot("EURUSD").warmupBarCount100()).isEqualTo(289);
            assertThat(registry.snapshot("EURUSD").bridgeEndTsUtc()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));
            assertThat(historyPort.requests()).singleElement().satisfies(request -> {
                assertThat(request.fromInclusive()).isEqualTo(Instant.parse("2026-03-22T11:59:57.001Z"));
                assertThat(request.toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:20Z"));
            });

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

    @Test
    void bridgeUsesExistingWarmupWhenNoBrokerTicksAreNeeded() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:10Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(List.of(List.of()), () -> {
        });
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T12:00:05Z"));
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T12:00:00Z"),
                    "run-1",
                    Duration.ofMinutes(15),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    289
            ));

            assertThat(result.ready()).isTrue();
            assertThat(historyPort.requests()).singleElement().satisfies(request -> {
                assertThat(request.fromInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00.001Z"));
                assertThat(request.toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:10Z"));
            });
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(server.getRequestCount()).isEqualTo(1);
            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");
        }
    }

    @Test
    void bridgeDoesNotSkipTicksWhenCursorCatchesUpToNow() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(List.of(
                List.of(),
                List.of(new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:00:00.005Z"), 1.0850, 1.0852))
        ), () -> clock.advance(Duration.ofMillis(10)));
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T11:59:00Z"));
            server.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {
                              "ok": true,
                              "symbol": "EURUSD",
                              "ticks_received": 1,
                              "accepted_count": 1,
                              "dropped_count": 0,
                              "bar_completed": false,
                              "completed_bar_ticks": [],
                              "symbol_tick_seq": 1,
                              "last_tick_ts_utc": "2026-03-22T12:00:00.005Z",
                              "last_client_tick_seq": 1,
                              "bar_count": 289
                            }
                            """));
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T12:00:00.005Z"));
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T12:00:00Z"),
                    "run-1",
                    Duration.ofMinutes(5),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isTrue();
            assertThat(historyPort.requests()).hasSize(2);
            assertThat(historyPort.requests().get(0).fromInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));
            assertThat(historyPort.requests().get(0).toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00Z"));
            assertThat(historyPort.requests().get(1).fromInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00.001Z"));
            assertThat(historyPort.requests().get(1).toInclusive()).isEqualTo(Instant.parse("2026-03-22T12:00:00.010Z"));
            assertThat(registry.snapshot("EURUSD").bridgeEndTsUtc()).isEqualTo(Instant.parse("2026-03-22T12:00:00.005Z"));
        }
    }

    @Test
    void bridgeClampsHistoryRequestToBrokerLastTickBeforeBrokerCall() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:20Z"), ZoneId.of("UTC"));
        Instant brokerLastTickTs = Instant.parse("2026-03-22T12:00:00Z");
        List<WindowRequest> requests = new ArrayList<>();
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {
                              "ok": true,
                              "symbol": "EURUSD",
                              "ticks_received": 1,
                              "accepted_count": 1,
                              "dropped_count": 0,
                              "bar_completed": false,
                              "completed_bar_ticks": [],
                              "symbol_tick_seq": 1,
                              "last_tick_ts_utc": "2026-03-22T12:00:00Z",
                              "last_client_tick_seq": 1,
                              "bar_count": 289
                            }
                            """));
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T12:00:00Z"));
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerHistoryPort historyPort = new BrokerHistoryPort() {
                @Override
                public List<RuntimeTick> getTicks(String symbol, Instant fromInclusive, Instant toInclusive) {
                    requests.add(new WindowRequest(fromInclusive, toInclusive));
                    if (toInclusive.isAfter(brokerLastTickTs)) {
                        throw new IllegalStateException("\"to\" parameter can't be greater than time of the last tick for this instrument");
                    }
                    return List.of(new RuntimeTick("EURUSD", brokerLastTickTs, 1.0852, 1.0854));
                }

                @Override
                public Instant getLastTickTimestamp(String symbol) {
                    return brokerLastTickTs;
                }
            };
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:59Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isTrue();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(requests).singleElement().satisfies(request -> {
                assertThat(request.fromInclusive()).isEqualTo(Instant.parse("2026-03-22T11:59:59.001Z"));
                assertThat(request.toInclusive()).isEqualTo(brokerLastTickTs);
            });
            assertThat(server.getRequestCount()).isEqualTo(2);
        }
    }

    @Test
    void bridgeFailureIsContainedToErrorPausedResult() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC"));
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader((symbol, fromInclusive, toInclusive) -> {
                throw new IllegalStateException("history unavailable");
            }, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:00Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isFalse();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").lastFailureReason()).contains("history unavailable");
        }
    }

    @Test
    void bridgeFailureIncludesNestedHistoryCauseDetails() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC"));
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            PythonPredictionClient predictionClient = new PythonPredictionClient(HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader((symbol, fromInclusive, toInclusive) -> {
                throw new RuntimeException(
                        "Error while loading ticks",
                        new IllegalStateException("\"to\" parameter can't be greater than time of the last tick for this instrument")
                );
            }, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:00Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isFalse();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").lastFailureReason())
                    .contains("Error while loading ticks")
                    .contains("\"to\" parameter can't be greater than time of the last tick for this instrument");
        }
    }

    @Test
    void bridgeRetriesTransient599AndReachesReady() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:20Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(
                List.of(
                        List.of(),
                        List.of(new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:00:00Z"), 1.0850, 1.0852)),
                        List.of(new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:00:00Z"), 1.0850, 1.0852))
                ),
                () -> {}
        );
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            // Feed status → stale
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T10:00:00Z"));
            // First /ticks/batch → disconnect (simulates 599 / IOException)
            server.enqueue(new MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_END));
            // Second /ticks/batch → success, bar_count >= 289
            server.enqueue(new MockResponse()
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                            {"ok":true,"symbol":"EURUSD","ticks_received":1,"accepted_count":1,
                            "dropped_count":0,"bar_completed":false,"completed_bar_ticks":[],
                            "symbol_tick_seq":1,"last_tick_ts_utc":"2026-03-22T12:00:00Z",
                            "last_client_tick_seq":1,"bar_count":289}
                            """));
            // Feed status → fresh (satisfies warmup+freshness)
            server.enqueue(feedStatusResponse("EURUSD", "2026-03-22T12:00:20Z"));

            PythonPredictionClient predictionClient = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:59Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isTrue();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
            assertThat(server.getRequestCount()).isEqualTo(4);
            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");

            RecordedRequest failedBatchRequest = server.takeRequest();
            assertThat(failedBatchRequest.getPath()).isEqualTo("/ticks/batch");
            TickBatchRequestPayload failedBatchPayload = predictionClient.objectMapper()
                    .readValue(failedBatchRequest.getBody().readUtf8(), TickBatchRequestPayload.class);

            RecordedRequest successfulBatchRequest = server.takeRequest();
            assertThat(successfulBatchRequest.getPath()).isEqualTo("/ticks/batch");
            TickBatchRequestPayload successfulBatchPayload = predictionClient.objectMapper()
                    .readValue(successfulBatchRequest.getBody().readUtf8(), TickBatchRequestPayload.class);

            assertThat(failedBatchPayload.ticks())
                    .extracting(tick -> tick.clientTickSeq())
                    .containsExactly(1L);
            assertThat(successfulBatchPayload.ticks())
                    .extracting(tick -> tick.clientTickSeq())
                    .containsExactly(1L);

            assertThat(server.takeRequest().getPath()).isEqualTo("/runtime/feed/status");
        }
    }

    @Test
    void bridgeTimesOutWhenAllTickBatchCallsAreTransient() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:00Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(
                List.of(
                        List.of(new RuntimeTick("EURUSD", Instant.parse("2026-03-22T11:59:00Z"), 1.0850, 1.0852)),
                        List.of(new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:09:00Z"), 1.0851, 1.0853))
                ),
                () -> clock.advance(Duration.ofMinutes(11))
        );
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            // Enqueue enough disconnects to cover all retries before the 20-minute deadline expires
            // (the clock advances 11 min per cycle via the FakeBrokerHistoryPort callback, so deadline is hit within 2 cycles)
            for (int i = 0; i < 10; i++) {
                server.enqueue(new MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_END));
            }

            PythonPredictionClient predictionClient = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:58:59Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isFalse();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").startupTimeoutReached()).isTrue();
        }
    }

    @Test
    void bridgeFailsImmediatelyOnNonTransientException() throws Exception {
        MutableClock clock = new MutableClock(Instant.parse("2026-03-22T12:00:20Z"), ZoneId.of("UTC"));
        FakeBrokerHistoryPort historyPort = new FakeBrokerHistoryPort(
                List.of(List.of(
                        new RuntimeTick("EURUSD", Instant.parse("2026-03-22T12:00:00Z"), 1.0850, 1.0852)
                )),
                () -> {}
        );
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(422)
                    .setHeader("Content-Type", "application/json")
                    .setBody("{\"detail\":\"bad request\"}"));

            PythonPredictionClient predictionClient = new PythonPredictionClient(
                    HttpClient.newHttpClient(), server.url("/").uri());
            BrokerBridgeLoader loader = new BrokerBridgeLoader(historyPort, predictionClient, registry, clock);

            BrokerBridgeLoader.BridgeResult result = loader.bridge(new BrokerBridgeLoader.BridgeConfig(
                    "EURUSD",
                    Instant.parse("2026-03-22T11:59:59Z"),
                    "run-1",
                    Duration.ofMinutes(60),
                    Duration.ofSeconds(30),
                    Duration.ofMinutes(20),
                    289,
                    0
            ));

            assertThat(result.ready()).isFalse();
            assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
            assertThat(registry.snapshot("EURUSD").startupTimeoutReached()).isFalse();
            assertThat(server.getRequestCount()).isEqualTo(1);
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
