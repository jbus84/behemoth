package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LiveReadinessStatusWriterTest {
    @TempDir
    Path tempDir;

    @Test
    void statusWriterPersistsFullSchemaVersionedSnapshotFromRegistry() throws Exception {
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(
                java.util.List.of("EURUSD", "GBPUSD"),
                30
        );
        Instant parquetTail = Instant.parse("2026-03-21T23:59:59Z");
        Instant bridgeStart = Instant.parse("2026-03-22T12:00:00Z");
        Instant bridgeRequestedTo = Instant.parse("2026-03-22T12:34:20Z");
        Instant bridgeEnd = Instant.parse("2026-03-22T12:34:24Z");
        Instant readyAt = Instant.parse("2026-03-22T12:34:40Z");
        Instant failedAt = Instant.parse("2026-03-22T12:34:41Z");
        Instant asOf = Instant.parse("2026-03-22T12:34:56Z");

        registry.markParquetWarming("EURUSD", Instant.parse("2026-03-22T11:55:00Z"), parquetTail);
        registry.markBridging("EURUSD", bridgeStart);
        registry.recordBridgeProgress("EURUSD", bridgeRequestedTo, bridgeEnd);
        registry.markBridgeComplete("EURUSD", bridgeEnd);
        registry.markReady("EURUSD", readyAt, 312, bridgeEnd);

        registry.markParquetWarming("GBPUSD", Instant.parse("2026-03-22T11:56:00Z"), parquetTail.minusSeconds(10));
        registry.markStartupTimeoutReached("GBPUSD");
        registry.markErrorPaused("GBPUSD", failedAt, "bridge_timeout");

        LiveReadinessSnapshot snapshot = registry.liveSnapshot(asOf, "jforex_live");
        Path out = tempDir.resolve("data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json");
        LiveReadinessStatusWriter writer = new LiveReadinessStatusWriter(out, new ObjectMapper());

        writer.write(snapshot);

        ObjectMapper mapper = new ObjectMapper();
        JsonNode json = mapper.readTree(Files.readString(out));
        JsonNode expected = mapper.readTree("""
                {
                  "schema_version": 1,
                  "as_of_utc": "2026-03-22T12:34:56Z",
                  "run_id": "jforex_live",
                  "session_bridge_ready_symbol_count": 0,
                  "session_tradable_symbol_count": 0,
                  "session_execution_eligible_symbol_count": 0,
                  "session_total_symbol_count": 2,
                  "symbols": [
                    {
                      "symbol": "EURUSD",
                      "state": "STALE_PAUSED",
                      "bridge_entries_allowed": false,
                      "deployment_state": "live_loaded",
                      "entries_allowed": false,
                      "execution_allowed": false,
                      "parquet_tail_ts_utc": "2026-03-21T23:59:59Z",
                      "bridge_start_ts_utc": "2026-03-22T12:00:00Z",
                      "bridge_end_ts_utc": "2026-03-22T12:34:24Z",
                      "bridge_last_requested_to_utc": "2026-03-22T12:34:20Z",
                      "last_ingested_tick_ts_utc": "2026-03-22T12:34:24Z",
                      "staleness_seconds": 32,
                      "warmup_bar_count_100": 312,
                      "startup_timeout_reached": false,
                      "last_failure_reason": "",
                      "last_state_transition_utc": "2026-03-22T12:34:56Z"
                    },
                    {
                      "symbol": "GBPUSD",
                      "state": "ERROR_PAUSED",
                      "bridge_entries_allowed": false,
                      "deployment_state": "live_loaded",
                      "entries_allowed": false,
                      "execution_allowed": false,
                      "parquet_tail_ts_utc": "2026-03-21T23:59:49Z",
                      "bridge_start_ts_utc": "",
                      "bridge_end_ts_utc": "",
                      "bridge_last_requested_to_utc": "",
                      "last_ingested_tick_ts_utc": "",
                      "staleness_seconds": 0,
                      "warmup_bar_count_100": 0,
                      "startup_timeout_reached": true,
                      "last_failure_reason": "bridge_timeout",
                      "last_state_transition_utc": "2026-03-22T12:34:41Z"
                    }
                  ]
                }
                """);

        assertThat(json).isEqualTo(expected);
    }

    @Test
    void statusWriterSeparatesBridgeReadinessFromGovernanceExecutionEligibility() throws Exception {
        Instant asOf = Instant.parse("2026-04-22T16:20:15Z");
        LiveReadinessSnapshot snapshot = new LiveReadinessSnapshot(
                asOf,
                "jforex_live",
                2,
                2,
                java.util.List.of(
                        new SymbolReadinessSnapshot(
                                "EURUSD",
                                SymbolReadinessState.READY,
                                true,
                                Instant.parse("2026-04-10T20:59:59Z"),
                                Instant.parse("2026-04-22T16:11:13Z"),
                                null,
                                Instant.parse("2026-04-10T21:59:59Z"),
                                Instant.parse("2026-04-22T16:20:15Z"),
                                0,
                                3000,
                                false,
                                "",
                                Instant.parse("2026-04-22T16:11:14Z")
                        ),
                        new SymbolReadinessSnapshot(
                                "AUDUSD",
                                SymbolReadinessState.READY,
                                true,
                                Instant.parse("2026-04-10T20:59:59Z"),
                                Instant.parse("2026-04-22T16:11:14Z"),
                                null,
                                Instant.parse("2026-04-10T21:59:59Z"),
                                Instant.parse("2026-04-22T16:20:11Z"),
                                3,
                                3000,
                                false,
                                "",
                                Instant.parse("2026-04-22T16:11:16Z")
                        )
                )
        );
        Path out = tempDir.resolve("data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json");
        LiveReadinessStatusWriter writer = new LiveReadinessStatusWriter(
                out,
                new ObjectMapper(),
                symbol -> switch (symbol) {
                    case "AUDUSD" -> "no_go_not_promoted";
                    case "EURUSD" -> "live_loaded";
                    default -> "error";
                }
        );

        writer.write(snapshot);

        ObjectMapper mapper = new ObjectMapper();
        JsonNode json = mapper.readTree(Files.readString(out));

        assertThat(json.get("session_bridge_ready_symbol_count").asInt()).isEqualTo(2);
        assertThat(json.get("session_tradable_symbol_count").asInt()).isEqualTo(1);
        assertThat(json.get("session_execution_eligible_symbol_count").asInt()).isEqualTo(1);
        assertThat(json.get("session_total_symbol_count").asInt()).isEqualTo(2);

        JsonNode eurusd = json.get("symbols").get(0);
        assertThat(eurusd.get("state").asText()).isEqualTo("READY");
        assertThat(eurusd.get("bridge_entries_allowed").asBoolean()).isTrue();
        assertThat(eurusd.get("deployment_state").asText()).isEqualTo("live_loaded");
        assertThat(eurusd.get("entries_allowed").asBoolean()).isTrue();
        assertThat(eurusd.get("execution_allowed").asBoolean()).isTrue();

        JsonNode audusd = json.get("symbols").get(1);
        assertThat(audusd.get("state").asText()).isEqualTo("READY");
        assertThat(audusd.get("bridge_entries_allowed").asBoolean()).isTrue();
        assertThat(audusd.get("deployment_state").asText()).isEqualTo("no_go_not_promoted");
        assertThat(audusd.get("entries_allowed").asBoolean()).isFalse();
        assertThat(audusd.get("execution_allowed").asBoolean()).isFalse();
    }
}
