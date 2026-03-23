package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.RuntimeTick;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.time.Instant;
import java.util.List;
import java.util.TimeZone;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.SAME_THREAD)
class HistoricalWarmupLoaderTest {
    @TempDir
    Path tempDir;

    @Test
    void loaderKeepsWarmupTicksPlusPhaseRemainder() throws Exception {
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("ticks.parquet");
        Instant bridgeAnchorTs = Instant.parse("2025-07-07T08:21:15Z");
        writeParquetTicks(parquetFile, bridgeAnchorTs, 30_075, false);

        HistoricalWarmupLoader loader = new HistoricalWarmupLoader();

        WarmupSlice slice = loader.load(config(), tempDir, "EURUSD", bridgeAnchorTs);

        assertThat(slice.ticks()).hasSize(30_075);
        assertThat(slice.bridgeAnchorTs()).isEqualTo(bridgeAnchorTs.minusSeconds(1));
        assertThat(slice.ticks()).extracting(RuntimeTick::timestamp).last().isEqualTo(slice.bridgeAnchorTs());
    }

    @Test
    void loaderExcludesTickAtBridgeAnchor() throws Exception {
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("ticks.parquet");
        Instant bridgeAnchorTs = Instant.parse("2025-07-07T08:21:15Z");
        writeParquetTicks(parquetFile, bridgeAnchorTs, 30_076, true);

        HistoricalWarmupLoader loader = new HistoricalWarmupLoader();

        TimeZone original = TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("Europe/London"));
            WarmupSlice slice = loader.load(config(), tempDir, "EURUSD", bridgeAnchorTs);

            assertThat(slice.ticks()).hasSize(30_075);
            assertThat(slice.bridgeAnchorTs()).isEqualTo(bridgeAnchorTs.minusSeconds(1));
            assertThat(slice.ticks()).extracting(RuntimeTick::timestamp)
                    .doesNotContain(bridgeAnchorTs)
                    .last()
                    .isEqualTo(slice.bridgeAnchorTs());
        } finally {
            TimeZone.setDefault(original);
        }
    }

    @Test
    void loaderFailsWhenNoTicksFallWithinLookbackWindow() throws Exception {
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("ticks.parquet");
        Instant bridgeAnchorTs = Instant.parse("2025-07-07T08:21:15Z");
        writeParquetTicks(parquetFile, bridgeAnchorTs.minusSeconds(40L * 24L * 60L * 60L), 10, false);

        HistoricalWarmupLoader loader = new HistoricalWarmupLoader();

        assertThatThrownBy(() -> loader.load(config(), tempDir, "EURUSD", bridgeAnchorTs))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("No parquet ticks found for symbol EURUSD in lookback window");
    }

    private static void writeParquetTicks(Path parquetFile, Instant bridgeAnchorTs, int tickCount, boolean includeAnchor)
            throws Exception {
        String parquetPath = parquetFile.toAbsolutePath().toString().replace("\\", "\\\\").replace("'", "''");
        Instant firstTickTs = bridgeAnchorTs.minusSeconds(includeAnchor ? tickCount - 1L : tickCount);
        try (Connection conn = DriverManager.getConnection("jdbc:duckdb:")) {
            try (Statement st = conn.createStatement()) {
                st.execute(
                        "COPY ("
                                + "SELECT TIMESTAMP '" + firstTickTs.toString().replace("T", " ").replace("Z", "") + "'"
                                + " + (i * INTERVAL 1 SECOND) AS timestamp,"
                                + " 1.08500 + (i * 0.000001) AS bid,"
                                + " 1.08510 + (i * 0.000001) AS ask"
                                + " FROM range(" + tickCount + ") AS t(i)"
                                + ") TO '" + parquetPath + "' (FORMAT PARQUET)"
                );
            }
        }
    }

    private static JForexSessionConfig config() {
        return new JForexSessionConfig(
                URI.create("http://127.0.0.1:8000"),
                URI.create("http://127.0.0.1/test.jnlp"),
                "user",
                "pass",
                "DU123",
                List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"),
                Instant.parse("2025-07-07T00:01:00Z"),
                Path.of("build/test-reports"),
                "test-run",
                true,
                10_000.0,
                16,
                900L,
                false,
                60,
                false,
                "",
                0,
                true,
                30_000,
                31,
                60,
                30,
                20
        );
    }
}
