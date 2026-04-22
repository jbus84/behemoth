package com.behemoth.jforex.live;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public final class LiveReadinessStatusWriter {
    private static final int SCHEMA_VERSION = 1;
    private static final String LIVE_LOADED = "live_loaded";
    private static final String NO_GO_NOT_PROMOTED = "no_go_not_promoted";

    private final Path target;
    private final ObjectMapper objectMapper;
    private final Function<String, String> deploymentStateResolver;

    public LiveReadinessStatusWriter(Path target, ObjectMapper objectMapper) {
        this(target, objectMapper, symbol -> LIVE_LOADED);
    }

    public LiveReadinessStatusWriter(
            Path target,
            ObjectMapper objectMapper,
            Function<String, String> deploymentStateResolver
    ) {
        this.target = Objects.requireNonNull(target, "target");
        this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
        this.deploymentStateResolver = Objects.requireNonNull(deploymentStateResolver, "deploymentStateResolver");
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
        var symbolRows = snapshot.symbols().stream().map(this::toJson).toList();
        long bridgeReadyCount = symbolRows.stream()
                .filter(row -> Boolean.TRUE.equals(row.get("bridge_entries_allowed")))
                .count();
        long executionEligibleCount = symbolRows.stream()
                .filter(row -> Boolean.TRUE.equals(row.get("execution_allowed")))
                .count();
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("schema_version", SCHEMA_VERSION);
        root.put("as_of_utc", format(snapshot.asOfUtc()));
        root.put("run_id", snapshot.runId());
        root.put("session_bridge_ready_symbol_count", bridgeReadyCount);
        root.put("session_tradable_symbol_count", executionEligibleCount);
        root.put("session_execution_eligible_symbol_count", executionEligibleCount);
        root.put("session_total_symbol_count", snapshot.sessionTotalSymbolCount());
        root.put("symbols", symbolRows);
        return root;
    }

    private Map<String, Object> toJson(SymbolReadinessSnapshot snapshot) {
        String deploymentState = normalizeDeploymentState(deploymentStateResolver.apply(snapshot.symbol()));
        boolean bridgeEntriesAllowed = snapshot.entriesAllowed();
        boolean executionAllowed = bridgeEntriesAllowed && LIVE_LOADED.equals(deploymentState);
        Map<String, Object> symbol = new LinkedHashMap<>();
        symbol.put("symbol", snapshot.symbol());
        symbol.put("state", snapshot.state().name());
        symbol.put("bridge_entries_allowed", bridgeEntriesAllowed);
        symbol.put("deployment_state", deploymentState);
        symbol.put("entries_allowed", executionAllowed);
        symbol.put("execution_allowed", executionAllowed);
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

    private static String normalizeDeploymentState(String deploymentState) {
        String normalized = Objects.requireNonNullElse(deploymentState, "").trim();
        return normalized.isEmpty() ? "error" : normalized;
    }

    public static Function<String, String> deploymentStateResolverForGovernanceDir(Path governanceDir) {
        Path root = Objects.requireNonNull(governanceDir, "governanceDir");
        return symbol -> {
            String normalized = Objects.requireNonNull(symbol, "symbol").trim().toUpperCase();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("symbol must not be blank");
            }
            String lockName = normalized.toLowerCase() + "_oco_live_lock.json";
            return Files.exists(root.resolve(lockName)) ? LIVE_LOADED : NO_GO_NOT_PROMOTED;
        };
    }
}
