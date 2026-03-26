package com.behemoth.jforex.local;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ParquetTickLoaderPhaseAlignmentTest {

    @TempDir
    Path tempDir;

    @Test
    void load_usesFullPreStartTickCountForPhaseAlignment_notOnlyLookbackWindow() throws Exception {
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("phase.parquet");

        try (Connection conn = DriverManager.getConnection("jdbc:duckdb:")) {
            try (Statement st = conn.createStatement()) {
                st.execute(
                        "COPY ("
                                + "SELECT * FROM (VALUES "
                                + "(TIMESTAMPTZ '2025-07-05T00:00:01Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-05T00:00:02Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-05T00:00:03Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-05T00:00:04Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-05T00:00:05Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:01Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:02Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:03Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:04Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:05Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:06Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:07Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:08Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:09Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-06T00:00:10Z', 1.1000, 1.1001),"
                                + "(TIMESTAMPTZ '2025-07-07T00:00:01Z', 1.1000, 1.1001)"
                                + ") AS t(timestamp, bid, ask)"
                                + ") TO '" + parquetFile.toAbsolutePath() + "' (FORMAT PARQUET)"
                );
            }
        }

        LocalJForexHarnessConfig config = new LocalJForexHarnessConfig(
                URI.create("http://127.0.0.1:8000"),
                List.of("EURUSD"),
                Instant.parse("2025-07-07T00:00:00Z"),
                Instant.parse("2025-07-08T00:00:00Z"),
                tempDir.resolve("reports"),
                "test-run",
                false,
                10000.0,
                1,
                900L,
                60,
                false,
                "",
                0,
                tempDir,
                0,
                1,
                4,
                100000.0
        );

        ParquetTickLoader.TickWindow window = new ParquetTickLoader().load(config, "EURUSD");

        // Full pre-start tick count is 15 -> remainder 3 when phase_bar_ticks=4.
        // Only 10 of those ticks are inside the 1-day lookback window, whose remainder is 2.
        // The loader must preserve the full-history phase and keep the last 3 warmup ticks.
        assertThat(window.warmup()).extracting(tick -> tick.timestamp().toString()).containsExactly(
                "2025-07-06T00:00:08Z",
                "2025-07-06T00:00:09Z",
                "2025-07-06T00:00:10Z"
        );
    }
}
