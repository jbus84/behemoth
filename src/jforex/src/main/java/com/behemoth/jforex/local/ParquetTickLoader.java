package com.behemoth.jforex.local;

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
import java.util.TimeZone;

public final class ParquetTickLoader {
    private static final TimeZone UTC_TZ = TimeZone.getTimeZone("UTC");
    public TickWindow load(LocalJForexHarnessConfig config, String symbol) {
        String sym = normalizeSymbol(symbol);
        List<Path> files = parquetFiles(config.tickRoot(), sym);
        if (files.isEmpty()) {
            throw new IllegalArgumentException("No parquet files found for symbol " + sym + " under " + config.tickRoot());
        }
        String parquetExpr = parquetExpression(files);
        Instant lookbackStart = config.startUtc().minus(config.lookbackDays(), ChronoUnit.DAYS);
        try (Connection connection = DriverManager.getConnection("jdbc:duckdb:")) {
            int fullPreCount = countBeforeStart(connection, parquetExpr, null, config.startUtc());
            int keep = config.warmupTicks() + (fullPreCount % config.phaseBarTicks());
            List<RuntimeTick> warmup = loadRowsDescending(connection, parquetExpr, lookbackStart, config.startUtc(), keep, sym);
            warmup.sort(Comparator.comparing(RuntimeTick::timestamp));
            List<RuntimeTick> stream = loadRowsAscending(connection, parquetExpr, config.startUtc(), config.endUtc(), sym);
            return new TickWindow(warmup, stream);
        } catch (Exception exc) {
            throw new IllegalStateException("Failed to load local JForex parquet ticks for " + sym, exc);
        }
    }

    private static int countBeforeStart(Connection connection, String parquetExpr, Instant lookbackStart, Instant startUtc) throws Exception {
        String sql = lookbackStart == null
                ? "SELECT COUNT(*) FROM read_parquet(" + parquetExpr + ") WHERE timestamp < ?"
                : "SELECT COUNT(*) FROM read_parquet(" + parquetExpr + ") WHERE timestamp >= ? AND timestamp < ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            if (lookbackStart == null) {
                ps.setTimestamp(1, Timestamp.from(startUtc));
            } else {
                ps.setTimestamp(1, Timestamp.from(lookbackStart));
                ps.setTimestamp(2, Timestamp.from(startUtc));
            }
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getInt(1) : 0;
            }
        }
    }

    private static List<RuntimeTick> loadRowsDescending(
            Connection connection,
            String parquetExpr,
            Instant startUtc,
            Instant endUtc,
            int limit,
            String symbol
    ) throws Exception {
        String sql = "SELECT timestamp, bid, ask FROM read_parquet(" + parquetExpr + ") "
                + "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp DESC LIMIT ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setTimestamp(1, Timestamp.from(startUtc));
            ps.setTimestamp(2, Timestamp.from(endUtc));
            ps.setInt(3, limit);
            return collectTicks(ps.executeQuery(), symbol);
        }
    }

    private static List<RuntimeTick> loadRowsAscending(
            Connection connection,
            String parquetExpr,
            Instant startUtc,
            Instant endUtc,
            String symbol
    ) throws Exception {
        String sql = "SELECT timestamp, bid, ask FROM read_parquet(" + parquetExpr + ") "
                + "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setTimestamp(1, Timestamp.from(startUtc));
            ps.setTimestamp(2, Timestamp.from(endUtc));
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
            return quoted.getFirst();
        }
        return "[" + String.join(", ", quoted) + "]";
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }

    public record TickWindow(List<RuntimeTick> warmup, List<RuntimeTick> stream) {
    }
}
