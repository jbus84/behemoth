package com.behemoth.jforex.config;

import java.net.URI;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
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
        int metricsPort,
        boolean newEntriesEnabled,
        boolean liveReadinessEnabled,
        int liveWarmupTicks,
        int liveLookbackDays,
        int liveBridgeWindowMinutes,
        int liveFreshnessSeconds,
        int liveStartupBridgeTimeoutMinutes,
        int liveBarAlignTicks
) {
    private static final boolean DEFAULT_LIVE_READINESS_ENABLED = true;
    private static final int DEFAULT_LIVE_WARMUP_TICKS = 30_000;
    private static final int DEFAULT_LIVE_LOOKBACK_DAYS = 31;
    private static final int DEFAULT_LIVE_BRIDGE_WINDOW_MINUTES = 60;
    private static final int DEFAULT_LIVE_FRESHNESS_SECONDS = 30;
    private static final int DEFAULT_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES = 20;
    private static final int DEFAULT_LIVE_BAR_ALIGN_TICKS = 1000;

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
        if (liveWarmupTicks < 0
                || liveLookbackDays < 0
                || liveBridgeWindowMinutes < 0
                || liveFreshnessSeconds < 0
                || liveStartupBridgeTimeoutMinutes < 0) {
            throw new IllegalArgumentException("live readiness tuning values must be >= 0");
        }
        if (liveBarAlignTicks <= 0) {
            throw new IllegalArgumentException("liveBarAlignTicks must be > 0");
        }
    }

    public JForexSessionConfig(
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
        this(
                apiBaseUri,
                jnlpUri,
                username,
                password,
                accountId,
                instruments,
                startUtc,
                endUtc,
                reportDir,
                runId,
                riskEnabled,
                requestedVolumeUnits,
                tickBatchSize,
                orderTtlSeconds,
                nativeOcoEnabled,
                apiTimeoutSeconds,
                metricsEnabled,
                metricsHost,
                metricsPort,
                true
        );
    }

    public JForexSessionConfig(
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
            int metricsPort,
            boolean newEntriesEnabled
    ) {
        this(
                apiBaseUri,
                jnlpUri,
                username,
                password,
                accountId,
                instruments,
                startUtc,
                endUtc,
                reportDir,
                runId,
                riskEnabled,
                requestedVolumeUnits,
                tickBatchSize,
                orderTtlSeconds,
                nativeOcoEnabled,
                apiTimeoutSeconds,
                metricsEnabled,
                metricsHost,
                metricsPort,
                newEntriesEnabled,
                DEFAULT_LIVE_READINESS_ENABLED,
                DEFAULT_LIVE_WARMUP_TICKS,
                DEFAULT_LIVE_LOOKBACK_DAYS,
                DEFAULT_LIVE_BRIDGE_WINDOW_MINUTES,
                DEFAULT_LIVE_FRESHNESS_SECONDS,
                DEFAULT_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES,
                DEFAULT_LIVE_BAR_ALIGN_TICKS
        );
    }

    public static JForexSessionConfig fromEnvironment(boolean testerMode) {
        return fromEnvironment(testerMode, System.getenv());
    }

    public static JForexSessionConfig fromEnvironment(boolean testerMode, Map<String, String> environment) {
        Instant start = testerMode
                ? Instant.parse(requiredSetting(environment, "BEHEMOTH_JFOREX_START_UTC"))
                : Instant.now();
        Instant end = testerMode
                ? Instant.parse(requiredSetting(environment, "BEHEMOTH_JFOREX_END_UTC"))
                : start.plusSeconds(60);
        String defaultLiveReadinessEnabled = testerMode
                ? Boolean.toString(false)
                : Boolean.toString(DEFAULT_LIVE_READINESS_ENABLED);
        return new JForexSessionConfig(
                URI.create(setting(environment, "BEHEMOTH_API_BASE_URI", "http://127.0.0.1:8000")),
                URI.create(requiredSetting(environment, "BEHEMOTH_JFOREX_JNLP_URI")),
                requiredSetting(environment, "BEHEMOTH_JFOREX_USERNAME"),
                requiredSetting(environment, "BEHEMOTH_JFOREX_PASSWORD"),
                setting(environment, "BEHEMOTH_JFOREX_ACCOUNT_ID", ""),
                List.of(setting(environment, "BEHEMOTH_JFOREX_INSTRUMENTS", "GBPUSD").split(",")),
                start,
                end,
                Path.of(setting(
                        environment,
                        "BEHEMOTH_JFOREX_REPORT_DIR",
                        "data/analysis/backtest_reconcile"
                )),
                setting(environment, "BEHEMOTH_JFOREX_RUN_ID", "jforex_adapter"),
                Boolean.parseBoolean(setting(environment, "BEHEMOTH_JFOREX_RISK_ENABLED", "true")),
                Double.parseDouble(setting(environment, "BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS", "10000")),
                Integer.parseInt(setting(environment, "BEHEMOTH_JFOREX_TICK_BATCH_SIZE", "16")),
                Long.parseLong(setting(environment, "BEHEMOTH_JFOREX_ORDER_TTL_SECONDS", "900")),
                Boolean.parseBoolean(setting(environment, "BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED", "false")),
                Integer.parseInt(setting(environment, "BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS", "60")),
                Boolean.parseBoolean(setting(environment, "BEHEMOTH_JFOREX_METRICS_ENABLED", "true")),
                setting(environment, "BEHEMOTH_JFOREX_METRICS_HOST", "127.0.0.1"),
                Integer.parseInt(setting(environment, "BEHEMOTH_JFOREX_METRICS_PORT", "9464")),
                Boolean.parseBoolean(setting(environment, "BEHEMOTH_JFOREX_NEW_ENTRIES_ENABLED", "true")),
                Boolean.parseBoolean(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_READINESS_ENABLED",
                        defaultLiveReadinessEnabled
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_WARMUP_TICKS",
                        Integer.toString(DEFAULT_LIVE_WARMUP_TICKS)
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_LOOKBACK_DAYS",
                        Integer.toString(DEFAULT_LIVE_LOOKBACK_DAYS)
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_BRIDGE_WINDOW_MINUTES",
                        Integer.toString(DEFAULT_LIVE_BRIDGE_WINDOW_MINUTES)
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_FRESHNESS_SECONDS",
                        Integer.toString(DEFAULT_LIVE_FRESHNESS_SECONDS)
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES",
                        Integer.toString(DEFAULT_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES)
                )),
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS",
                        Integer.toString(DEFAULT_LIVE_BAR_ALIGN_TICKS)
                ))
        );
    }

    private static String requiredSetting(Map<String, String> environment, String key) {
        return Objects.requireNonNull(setting(environment, key, null), key + " must be set");
    }

    private static String setting(Map<String, String> environment, String key, String defaultValue) {
        return environment.getOrDefault(key, defaultValue);
    }
}
