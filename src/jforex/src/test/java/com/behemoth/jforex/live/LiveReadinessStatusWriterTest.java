package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LiveReadinessStatusWriterTest {
    @TempDir
    Path tempDir;

    @Test
    void statusWriterPersistsSchemaVersionedSnapshotAtomically() throws Exception {
        LiveReadinessSnapshot snapshot = new LiveReadinessSnapshot(
                Instant.parse("2026-03-22T12:34:56Z"),
                "jforex_live",
                0,
                6,
                List.of(new SymbolReadinessSnapshot(
                        "EURUSD",
                        SymbolReadinessState.BRIDGING,
                        false,
                        Instant.parse("2026-03-21T23:59:59Z"),
                        Instant.parse("2026-03-22T12:00:00Z"),
                        Instant.parse("2026-03-22T12:34:24Z"),
                        Instant.parse("2026-03-22T12:34:30Z"),
                        Instant.parse("2026-03-22T12:34:40Z"),
                        16L,
                        312,
                        false,
                        "",
                        Instant.parse("2026-03-22T12:34:41Z")
                ))
        );
        Path out = tempDir.resolve("data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json");
        LiveReadinessStatusWriter writer = new LiveReadinessStatusWriter(out, new ObjectMapper());

        writer.write(snapshot);

        JsonNode json = new ObjectMapper().readTree(Files.readString(out));
        assertThat(json.get("schema_version").asInt()).isEqualTo(1);
        assertThat(json.get("symbols").get(0).get("bridge_end_ts_utc").asText()).isNotBlank();
    }
}
