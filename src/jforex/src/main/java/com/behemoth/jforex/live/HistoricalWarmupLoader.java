package com.behemoth.jforex.live;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.RuntimeTick;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.TimeZone;

public final class HistoricalWarmupLoader {
    private static final TimeZone UTC_TZ = TimeZone.getTimeZone("UTC");
    private static final int PHASE_BAR_TICKS = 100;

    public WarmupSlice load(JForexSessionConfig config, Path tickRoot, String symbol, Instant bridgeAnchorTs) {
        Objects.requireNonNull(config, "config");
        Objects.requireNonNull(tickRoot, "tickRoot");
        Objects.requireNonNull(bridgeAnchorTs, "bridgeAnchorTs");

        String sym = normalizeSymbol(symbol);
        List<Path> files = parquetFiles(tickRoot, sym);
        if (files.isEmpty()) {
            throw new IllegalArgumentException("No parquet files found for symbol " + sym + " under " + tickRoot);
        }

        String parquetExpr = parquetExpression(files);
        Instant lookbackStart = bridgeAnchorTs.minus(config.liveLookbackDays(), ChronoUnit.DAYS);
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:")) {
            int preCount = countBeforeAnchor(connection, parquetExpr, lookbackStart, bridgeAnchorTs);
            int keep = config.liveWarmupTicks() + (preCount % PHASE_BAR_TICKS);
            List<RuntimeTick> ticks = loadRowsDescending(connection, parquetExpr, lookbackStart, bridgeAnchorTs, keep, sym);
            ticks.sort(Comparator.comparing(RuntimeTick::timestamp));
            return new WarmupSlice(bridgeAnchorTs, ticks);
        } catch (Exception exc) {
            throw new IllegalStateException("Failed to load historical warmup parquet ticks for " + sym, exc);
        }
    }

    private static int countBeforeAnchor(Connection connection, String parquetExpr, Instant lookbackStart, Instant bridgeAnchorTs)
            throws Exception {
        String sql = "SELECT COUNT(*) FROM read_parquet(" + parquetExpr + ") WHERE timestamp >= ? AND timestamp < ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setTimestamp(1, Timestamp.from(lookbackStart));
            ps.setTimestamp(2, Timestamp.from(bridgeAnchorTs));
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getInt(1) : 0;
            }
        }
    }

    private static List<RuntimeTick> loadRowsDescending(
            Connection connection,
            String parquetExpr,
            Instant lookbackStart,
            Instant bridgeAnchorTs,
            int limit,
            String symbol
    ) throws Exception {
        if (limit <= 0) {
            return List.of();
        }
        String sql = "SELECT timestamp, bid, ask FROM read_parquet(" + parquetExpr + ") "
                + "WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setTimestamp(1, Timestamp.from(lookbackStart));
            ps.setTimestamp(2, Timestamp.from(bridgeAnchorTs));
            ps.setInt(3, limit);
            return collectTicks(ps.executeQuery(), symbol);
        }
    }

    private static List<RuntimeTick> collectTicks(ResultSet rs, String symbol) throws Exception {
        List<RuntimeTick> out = new ArrayList<>();
        while (rs.next()) {
            out.add(new RuntimeTick(
                    symbol,
                    rs.getTimestamp("timestamp", Calendar.getInstance(UTC_TZ)).toInstant(),
                    rs.getDouble("bid"),
                    rs.getDouble("ask")
            ));
        }
        return out;
    }

    private static List<Path> parquetFiles(Path tickRoot, String symbol) {
        Path symbolDir = tickRoot.resolve(symbol);
        if (!Files.isDirectory(symbolDir)) {
            return List.of();
        }
        try (var stream = Files.list(symbolDir)) {
            return stream
                    .filter(path -> path.getFileName().toString().endsWith(".parquet"))
                    .sorted()
                    .toList();
        } catch (Exception exc) {
            throw new IllegalStateException("Failed to list parquet files for " + symbol, exc);
        }
    }

    private static String parquetExpression(List<Path> files) {
        List<String> quoted = files.stream()
                .map(path -> "'" + path.toAbsolutePath().toString().replace("\\", "\\\\").replace("'", "''") + "'")
                .toList();
        if (quoted.size() == 1) {
            return quoted.get(0);
        }
        return "[" + String.join(", ", quoted) + "]";
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }
}

record WarmupSlice(Instant bridgeAnchorTs, List<RuntimeTick> ticks) {
    WarmupSlice {
        bridgeAnchorTs = Objects.requireNonNull(bridgeAnchorTs, "bridgeAnchorTs");
        ticks = List.copyOf(Objects.requireNonNull(ticks, "ticks"));
    }
}
