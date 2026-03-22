package com.behemoth.jforex.live;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class LiveReadinessStatusWriter {
    private static final int SCHEMA_VERSION = 1;

    private final Path target;
    private final ObjectMapper objectMapper;

    public LiveReadinessStatusWriter(Path target, ObjectMapper objectMapper) {
        this.target = Objects.requireNonNull(target, "target");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
    }

    public synchronized void write(LiveReadinessSnapshot snapshot) {
        Objects.requireNonNull(snapshot, "snapshot");
        Path parent = target.getParent();
        if (parent == null) {
            throw new IllegalArgumentException("target must have a parent directory");
        }
        try {
            Files.createDirectories(parent);
            Path tmp = Files.createTempFile(parent, target.getFileName().toString(), ".tmp");
            try {
                String json = objectMapper.writeValueAsString(toJson(snapshot));
                Files.writeString(tmp, json, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
                Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } finally {
                Files.deleteIfExists(tmp);
            }
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to write live readiness status: " + target, exc);
        }
    }

    private Map<String, Object> toJson(LiveReadinessSnapshot snapshot) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("schema_version", SCHEMA_VERSION);
        root.put("as_of_utc", format(snapshot.asOfUtc()));
        root.put("run_id", snapshot.runId());
        root.put("session_tradable_symbol_count", snapshot.sessionTradableSymbolCount());
        root.put("session_total_symbol_count", snapshot.sessionTotalSymbolCount());
        root.put("symbols", snapshot.symbols().stream().map(this::toJson).toList());
        return root;
    }

    private Map<String, Object> toJson(SymbolReadinessSnapshot snapshot) {
        Map<String, Object> symbol = new LinkedHashMap<>();
        symbol.put("symbol", snapshot.symbol());
        symbol.put("state", snapshot.state().name());
        symbol.put("entries_allowed", snapshot.entriesAllowed());
        symbol.put("parquet_tail_ts_utc", format(snapshot.parquetTailTsUtc()));
        symbol.put("bridge_start_ts_utc", format(snapshot.bridgeStartTsUtc()));
        symbol.put("bridge_end_ts_utc", format(snapshot.bridgeEndTsUtc()));
        symbol.put("bridge_last_requested_to_utc", format(snapshot.bridgeLastRequestedToUtc()));
        symbol.put("last_ingested_tick_ts_utc", format(snapshot.lastIngestedTickTsUtc()));
        symbol.put("staleness_seconds", snapshot.stalenessSeconds());
        symbol.put("warmup_bar_count_100", snapshot.warmupBarCount100());
        symbol.put("startup_timeout_reached", snapshot.startupTimeoutReached());
        symbol.put("last_failure_reason", snapshot.lastFailureReason());
        symbol.put("last_state_transition_utc", format(snapshot.lastStateTransitionUtc()));
        return symbol;
    }

    private static String format(Instant instant) {
        return instant == null ? "" : instant.toString();
    }
}
