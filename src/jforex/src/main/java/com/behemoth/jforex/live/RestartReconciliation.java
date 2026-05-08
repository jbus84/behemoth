package com.behemoth.jforex.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Supplier;

/**
 * View of {@code live_restart_reconciliation.json} relevant to readiness reporting.
 *
 * <p>Defaults to {@link #unknown()} when the file is missing or unreadable so that
 * readiness consumers fail safe — an invisible reconciliation outcome must not
 * read as green.
 */
public record RestartReconciliation(
        String verdict,
        List<String> reasons,
        boolean allowNewEntries
) {
    private static final String VERDICT_UNKNOWN = "UNKNOWN";

    public RestartReconciliation {
        Objects.requireNonNull(verdict, "verdict");
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
    }

    public static RestartReconciliation unknown() {
        return new RestartReconciliation(VERDICT_UNKNOWN, List.of(), false);
    }

    public static Supplier<RestartReconciliation> resolverForRuntimeDir(
            Path runtimeDir, ObjectMapper objectMapper
    ) {
        Objects.requireNonNull(runtimeDir, "runtimeDir");
        Objects.requireNonNull(objectMapper, "objectMapper");
        Path reconPath = runtimeDir.resolve("live_restart_reconciliation.json");
        return () -> readFrom(reconPath, objectMapper);
    }

    public static RestartReconciliation readFrom(Path reconPath, ObjectMapper objectMapper) {
        if (reconPath == null || !Files.exists(reconPath)) {
            return unknown();
        }
        try {
            JsonNode root = objectMapper.readTree(reconPath.toFile());
            String verdict = root.path("verdict").asText(VERDICT_UNKNOWN).trim();
            if (verdict.isEmpty()) {
                verdict = VERDICT_UNKNOWN;
            }
            JsonNode reasonsNode = root.path("reasons");
            List<String> reasons = new ArrayList<>();
            if (reasonsNode.isArray()) {
                for (JsonNode r : reasonsNode) {
                    reasons.add(r.asText(""));
                }
            }
            JsonNode eligNode = root.path("restart_eligibility");
            boolean allow = eligNode.path("allow_new_entries").asBoolean(false);
            return new RestartReconciliation(verdict, reasons, allow);
        } catch (IOException exc) {
            return unknown();
        }
    }
}
