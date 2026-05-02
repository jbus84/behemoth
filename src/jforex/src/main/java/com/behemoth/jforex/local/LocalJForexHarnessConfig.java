package com.behemoth.jforex.local;

import com.behemoth.jforex.config.JForexSessionConfig;
import java.net.URI;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record LocalJForexHarnessConfig(
        URI apiBaseUri,
        List<String> instruments,
        Instant startUtc,
        Instant endUtc,
        Path reportDir,
        String runId,
        boolean riskEnabled,
        double requestedVolumeUnits,
        int tickBatchSize,
        long orderTtlSeconds,
        int apiTimeoutSeconds,
        boolean metricsEnabled,
        String metricsHost,
        int metricsPort,
        Path tickRoot,
        int warmupTicks,
        int lookbackDays,
        int barAlignTicks,
        double startingBalance
) {
    public LocalJForexHarnessConfig {
        apiBaseUri = Objects.requireNonNull(apiBaseUri, "apiBaseUri");
        instruments = List.copyOf(Objects.requireNonNull(instruments, "instruments"));
        startUtc = Objects.requireNonNull(startUtc, "startUtc");
        endUtc = Objects.requireNonNull(endUtc, "endUtc");
        reportDir = Objects.requireNonNull(reportDir, "reportDir");
        runId = Objects.requireNonNullElse(runId, "").trim();
        tickRoot = Objects.requireNonNull(tickRoot, "tickRoot");
        metricsHost = Objects.requireNonNullElse(metricsHost, "").trim();
        if (instruments.isEmpty()) {
            throw new IllegalArgumentException("at least one instrument is required");
        }
        if (!startUtc.isBefore(endUtc)) {
            throw new IllegalArgumentException("startUtc must be before endUtc");
        }
        if (requestedVolumeUnits <= 0.0) {
            throw new IllegalArgumentException("requestedVolumeUnits must be > 0");
        }
        if (tickBatchSize <= 0 || warmupTicks < 0 || lookbackDays < 0 || barAlignTicks <= 0) {
            throw new IllegalArgumentException("tickBatchSize/barAlignTicks must be > 0; warmupTicks/lookbackDays must be >= 0");
        }
        if (orderTtlSeconds <= 0L) {
            throw new IllegalArgumentException("orderTtlSeconds must be > 0");
        }
        if (apiTimeoutSeconds <= 0) {
            throw new IllegalArgumentException("apiTimeoutSeconds must be > 0");
        }
        if (startingBalance <= 0.0) {
            throw new IllegalArgumentException("startingBalance must be > 0");
        }
        if (metricsEnabled && (metricsHost.isEmpty() || metricsPort <= 0)) {
            throw new IllegalArgumentException("metrics host/port must be set when metrics are enabled");
        }
    }

    public static LocalJForexHarnessConfig fromEnvironment() {
        return new LocalJForexHarnessConfig(
                URI.create(System.getenv().getOrDefault("BEHEMOTH_API_BASE_URI", "http://127.0.0.1:8000")),
                List.of(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_INSTRUMENTS", "GBPUSD").split(",")),
                Instant.parse(System.getenv("BEHEMOTH_LOCAL_JFOREX_START_UTC")),
                Instant.parse(System.getenv("BEHEMOTH_LOCAL_JFOREX_END_UTC")),
                Path.of(System.getenv().getOrDefault(
                        "BEHEMOTH_LOCAL_JFOREX_REPORT_DIR",
                        "data/analysis/backtest_reconcile"
                )),
                System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_RUN_ID", "local_jforex_surrogate"),
                Boolean.parseBoolean(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_RISK_ENABLED", "false")),
                Double.parseDouble(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_REQUESTED_VOLUME_UNITS", "10000")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_TICK_BATCH_SIZE", "256")),
                Long.parseLong(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_ORDER_TTL_SECONDS", "900")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_API_TIMEOUT_SECONDS", "60")),
                Boolean.parseBoolean(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_METRICS_ENABLED", "true")),
                System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_METRICS_HOST", "127.0.0.1"),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_METRICS_PORT", "9465")),
                Path.of(System.getenv().getOrDefault(
                        "BEHEMOTH_LOCAL_JFOREX_TICK_ROOT",
                        "/Users/danielfisher/Desktop/dukascopy_ticks"
                )),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_WARMUP_TICKS", "30000")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_LOOKBACK_DAYS", "31")),
                Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS", "1000")),
                Double.parseDouble(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_STARTING_BALANCE", "100000"))
        );
    }

    public JForexSessionConfig toSessionConfig() {
        return new JForexSessionConfig(
                apiBaseUri,
                URI.create("http://127.0.0.1/local-jforex"),
                "local",
                "local",
                "LOCAL",
                instruments,
                startUtc,
                endUtc,
                reportDir,
                runId,
                riskEnabled,
                requestedVolumeUnits,
                tickBatchSize,
                orderTtlSeconds,
                false,
                apiTimeoutSeconds,
                metricsEnabled,
                metricsHost,
                metricsPort
        );
    }
}
