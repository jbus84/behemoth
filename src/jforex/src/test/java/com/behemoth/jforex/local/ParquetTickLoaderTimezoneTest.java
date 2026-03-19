package com.behemoth.jforex.local;

import static org.assertj.core.api.Assertions.assertThat;

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

// TimeZone.setDefault is process-global; must run single-threaded to avoid racing with other tests
@Execution(ExecutionMode.SAME_THREAD)
class ParquetTickLoaderTimezoneTest {

    @TempDir
    Path tempDir;

    @Test
    void load_interpretsNaiveTimestampAsUtc_whenSystemTimezoneIsBst() throws Exception {
        // Arrange: write a parquet file with a naive TIMESTAMP (no TZ stored)
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("test.parquet");

        try (Connection conn = DriverManager.getConnection("jdbc:duckdb:")) {
            try (Statement st = conn.createStatement()) {
                st.execute(
                        "COPY (SELECT TIMESTAMP '2025-07-07 03:16:16.599' AS timestamp,"
                                + " 1.08500 AS bid, 1.08510 AS ask)"
                                + " TO '" + parquetFile.toAbsolutePath() + "' (FORMAT PARQUET)"
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
                256,
                900L,
                60,
                false,
                "",
                0,
                tempDir,
                0,
                0,
                1,
                100000.0
        );

        // Act: simulate a BST system (UTC+1 in July) to trigger the timezone bug
        TimeZone original = TimeZone.getDefault();
        ParquetTickLoader.TickWindow window;
        try {
            // TimeZone.setDefault is process-global; this test must run single-threaded.
            TimeZone.setDefault(TimeZone.getTimeZone("Europe/London"));
            window = new ParquetTickLoader().load(config, "EURUSD");
        } finally {
            TimeZone.setDefault(original);
        }

        // Assert: the tick timestamp must be interpreted as UTC, not shifted by BST
        assertThat(window.stream()).hasSize(1);
        RuntimeTick tick = window.stream().get(0);
        assertThat(tick.timestamp()).isEqualTo(Instant.parse("2025-07-07T03:16:16.599Z"));
    }
}
