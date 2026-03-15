package com.behemoth.jforex.config;

import java.net.URI;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * Shared connectivity and certification configuration for tester/demo/live runs.
 */
public record JForexSessionConfig(
        URI apiBaseUri,
        URI jnlpUri,
        String username,
        String password,
        String accountId,
        List<String> instruments,
        Instant startUtc,
        Instant endUtc,
        Path reportDir,
        String runId,
        boolean riskEnabled,
        double requestedVolumeUnits,
        int tickBatchSize,
        long orderTtlSeconds,
        boolean nativeOcoEnabled,
        int apiTimeoutSeconds,
        boolean metricsEnabled,
        String metricsHost,
        int metricsPort
) {
    public JForexSessionConfig {
        apiBaseUri = Objects.requireNonNull(apiBaseUri, "apiBaseUri");
        jnlpUri = Objects.requireNonNull(jnlpUri, "jnlpUri");
        username = Objects.requireNonNull(username, "username").trim();
        password = Objects.requireNonNull(password, "password").trim();
        accountId = accountId == null ? "" : accountId.trim();
        instruments = List.copyOf(Objects.requireNonNull(instruments, "instruments"));
        startUtc = Objects.requireNonNull(startUtc, "startUtc");
        endUtc = Objects.requireNonNull(endUtc, "endUtc");
        reportDir = Objects.requireNonNull(reportDir, "reportDir");
        runId = Objects.requireNonNullElse(runId, "").trim();
        if (username.isEmpty() || password.isEmpty()) {
            throw new IllegalArgumentException("username/password must not be blank");
        }
        if (instruments.isEmpty()) {
            throw new IllegalArgumentException("at least one instrument is required");
        }
        if (!startUtc.isBefore(endUtc)) {
            throw new IllegalArgumentException("startUtc must be before endUtc");
        }
        if (requestedVolumeUnits <= 0.0) {
            throw new IllegalArgumentException("requestedVolumeUnits must be > 0");
        }
        if (tickBatchSize <= 0) {
            throw new IllegalArgumentException("tickBatchSize must be > 0");
        }
        if (orderTtlSeconds <= 0L) {
            throw new IllegalArgumentException("orderTtlSeconds must be > 0");
        }
        if (apiTimeoutSeconds <= 0) {
            throw new IllegalArgumentException("apiTimeoutSeconds must be > 0");
        }
        metricsHost = Objects.requireNonNullElse(metricsHost, "").trim();
        if (metricsEnabled && metricsHost.isEmpty()) {
            throw new IllegalArgumentException("metricsHost must not be blank when metrics are enabled");
        }
        if (metricsEnabled && metricsPort <= 0) {
            throw new IllegalArgumentException("metricsPort must be > 0 when metrics are enabled");
        }
    }

    public static JForexSessionConfig fromEnvironment(boolean testerMode) {
        Instant start = testerMode
                ? Instant.parse(System.getenv("BEHEMOTH_JFOREX_START_UTC"))
                : Instant.now();
        Instant end = testerMode
                ? Instant.parse(System.getenv("BEHEMOTH_JFOREX_END_UTC"))
                : start.plusSeconds(60);
        return new JForexSessionConfig(
                URI.create(System.getenv().getOrDefault("BEHEMOTH_API_BASE_URI", "http://127.0.0.1:8000")),
                URI.create(System.getenv("BEHEMOTH_JFOREX_JNLP_URI")),
                System.getenv("BEHEMOTH_JFOREX_USERNAME"),
                System.getenv("BEHEMOTH_JFOREX_PASSWORD"),
                System.getenv().getOrDefault("BEHEMOTH_JFOREX_ACCOUNT_ID", ""),
                List.of(System.getenv().getOrDefault("BEHEMOTH_JFOREX_INSTRUMENTS", "GBPUSD").split(",")),
                start,
                end,
                Path.of(System.getenv().getOrDefault(
                        "BEHEMOTH_JFOREX_REPORT_DIR",
                        "data/analysis/backtest_reconcile"
                )),
                System.getenv().getOrDefault("BEHEMOTH_JFOREX_RUN_ID", "jforex_adapter"),
                Boolean.parseBoolean(System.getenv().getOrDefault("BEHEMOTH_JFOREX_RISK_ENABLED", "true")),
                Double.parseDouble(System.getenv().getOrDefault("BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS", "10000")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_JFOREX_TICK_BATCH_SIZE", "16")),
                Long.parseLong(System.getenv().getOrDefault("BEHEMOTH_JFOREX_ORDER_TTL_SECONDS", "900")),
                Boolean.parseBoolean(System.getenv().getOrDefault("BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED", "false")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS", "60")),
                Boolean.parseBoolean(System.getenv().getOrDefault("BEHEMOTH_JFOREX_METRICS_ENABLED", "true")),
                System.getenv().getOrDefault("BEHEMOTH_JFOREX_METRICS_HOST", "127.0.0.1"),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_JFOREX_METRICS_PORT", "9464"))
        );
    }
}
