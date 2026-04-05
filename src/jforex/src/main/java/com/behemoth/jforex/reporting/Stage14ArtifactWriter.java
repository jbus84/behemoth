package com.behemoth.jforex.reporting;

import com.behemoth.jforex.state.OcoGroupState;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Emits the Stage 14 CSV inputs expected by the JForex runtime certification script.
 */
public final class Stage14ArtifactWriter {
    private static final Set<String> REQUIRED_OPERATIONAL_STEPS = Set.of(
            "strategy_started",
            "subscribed",
            "feed_status",
            "account_snapshot"
    );

    private final Path reportDir;
    private final String artifactPrefix;
    private final List<EventRow> events = new ArrayList<>();

    public Stage14ArtifactWriter(Path reportDir) {
        this(reportDir, "jforex");
    }

    public Stage14ArtifactWriter(Path reportDir, String artifactPrefix) {
        this.reportDir = Objects.requireNonNull(reportDir, "reportDir");
        this.artifactPrefix = Objects.requireNonNull(artifactPrefix, "artifactPrefix").trim();
        if (this.artifactPrefix.isEmpty()) {
            throw new IllegalArgumentException("artifactPrefix must not be blank");
        }
    }

    public synchronized void recordPredictCycle(
            String symbol,
            Instant closeTs,
            int predictionCount,
            int selectedCount,
            int executableSelectedCount,
            int blockedCount,
            List<String> blockedReasons,
            List<Integer> completedBarTicks
    ) {
        Instant replayCloseTs = Objects.requireNonNull(closeTs, "closeTs");
        String blockedReasonsDetail = blockedReasons == null || blockedReasons.isEmpty()
                ? ""
                : ";blocked_reasons=" + String.join(",", blockedReasons);
        events.add(EventRow.pass(
                symbol,
                "signal",
                "predict_cycle",
                "prediction_count=" + predictionCount
                        + ";selected_count=" + selectedCount
                        + ";executable_selected_count=" + executableSelectedCount
                        + ";blocked_count=" + blockedCount
                        + blockedReasonsDetail
                        + ";close_ts=" + replayCloseTs
                        + ";completed_bar_ticks=" + completedBarTicks
        ));
    }

    public synchronized void recordPredictFailure(String symbol, String detail) {
        events.add(EventRow.fail(symbol, "signal", "predict_failure", detail));
    }

    public synchronized void recordOrderSubmitted(String symbol, String groupLabel, String legLabel) {
        events.add(EventRow.pass(symbol, "execution", "order_submitted", groupLabel + ":" + legLabel));
    }

    public synchronized void recordOrderSubmitFailure(String symbol, String groupLabel, String detail) {
        events.add(EventRow.fail(symbol, "execution", "order_submit_failure", groupLabel + ":" + detail));
    }

    public synchronized void recordFill(String symbol, String groupLabel, String legLabel) {
        events.add(EventRow.pass(symbol, "execution", "order_filled", groupLabel + ":" + legLabel));
    }

    public synchronized void recordTradeOutcome(
            String symbol,
            String groupLabel,
            String candidateUid,
            String sideLabel,
            double fillPrice,
            double closePrice,
            double pnlPips
    ) {
        events.add(EventRow.pass(
                symbol,
                "execution",
                "trade_outcome",
                "candidate_uid=" + candidateUid
                        + "|side=" + sideLabel
                        + "|fill_price=" + fillPrice
                        + "|close_price=" + closePrice
                        + "|pnl_pips=" + pnlPips
        ));
    }

    public synchronized void recordSiblingCancelAttempt(String symbol, String groupLabel, String legLabel) {
        events.add(EventRow.pass(symbol, "lifecycle", "sibling_cancel_attempt", groupLabel + ":" + legLabel));
    }

    public synchronized void recordSiblingCancelFailure(String symbol, String groupLabel, String detail) {
        events.add(EventRow.fail(symbol, "lifecycle", "sibling_cancel_failure", groupLabel + ":" + detail));
    }

    public synchronized void recordLifecycleViolation(String symbol, String groupLabel, String detail) {
        events.add(EventRow.fail(symbol, "lifecycle", "lifecycle_violation", groupLabel + ":" + detail));
    }

    public synchronized void recordTradeSyncFailure(String symbol, String operation, String detail) {
        events.add(EventRow.fail(symbol, "execution", operation, detail));
    }

    public synchronized void recordTradeOpenSync(String symbol, String brokerPosId) {
        events.add(EventRow.pass(symbol, "execution", "trade_open_synced", brokerPosId));
    }

    public synchronized void recordTradeTouchSync(String symbol, String brokerPosId) {
        events.add(EventRow.pass(symbol, "lifecycle", "trade_touch_synced", brokerPosId));
    }

    public synchronized void recordTradeUpdateSync(String symbol, String brokerPosId, String status) {
        events.add(EventRow.pass(symbol, "execution", "trade_update_synced", brokerPosId + ":" + status));
    }

    public synchronized void markOperationalStep(String symbol, String step, boolean pass, String detail) {
        events.add(new EventRow(Instant.now(), symbol, "operational", step, pass, detail));
    }

    public synchronized void writeReports(Collection<String> rawSymbols, Collection<OcoGroupState> groups) {
        try {
            Files.createDirectories(reportDir);
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to create JForex report directory", exc);
        }
        List<String> symbols = rawSymbols.stream()
                .map(sym -> sym == null ? "" : sym.trim().toUpperCase())
                .filter(sym -> !sym.isEmpty())
                .distinct()
                .sorted()
                .toList();
        for (String symbol : symbols) {
            List<EventRow> bySymbol = events.stream()
                    .filter(event -> symbol.equals(event.symbol()))
                    .toList();
            writeEvents(symbol, bySymbol);
            writeSignalSummary(symbol, bySymbol);
            writeExecutionSummary(symbol, bySymbol);
            writeLifecycleSummary(symbol, bySymbol, groups);
            writeOperationalSummary(symbol, bySymbol);
        }
    }

    private void writeEvents(String symbol, List<EventRow> rows) {
        List<String> lines = new ArrayList<>();
        lines.add("event_ts_utc,symbol,category,event_name,pass,detail");
        for (EventRow row : rows) {
            lines.add(csv(
                    row.eventTs().toString(),
                    row.symbol(),
                    row.category(),
                    row.eventName(),
                    Boolean.toString(row.pass()),
                    row.detail()
            ));
        }
        writeFile(reportDir.resolve(symbol + "_" + artifactPrefix + "_runtime_events.csv"), lines);
    }

    private void writeSignalSummary(String symbol, List<EventRow> rows) {
        long cycles = rows.stream().filter(row -> row.eventName().equals("predict_cycle")).count();
        boolean pass = cycles > 0 && rows.stream().noneMatch(row -> row.category().equals("signal") && !row.pass());
        List<String> lines = List.of(
                "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events",
                csv(
                        symbol,
                        Boolean.toString(pass),
                        Long.toString(cycles),
                        Long.toString(rows.stream().filter(row -> row.category().equals("signal") && !row.pass()).count())
                )
        );
        writeFile(reportDir.resolve(symbol + "_" + artifactPrefix + "_signal_parity_summary.csv"), lines);
    }

    private void writeExecutionSummary(String symbol, List<EventRow> rows) {
        long failed = rows.stream().filter(row -> row.category().equals("execution") && !row.pass()).count();
        long submittedOrders = rows.stream().filter(row -> row.eventName().equals("order_submitted")).count();
        boolean hadExecutableSelections = rows.stream()
                .filter(row -> row.category().equals("signal"))
                .filter(row -> row.eventName().equals("predict_cycle"))
                .map(EventRow::detail)
                .mapToInt(detail -> parsePredictCycleInt(detail, "executable_selected_count"))
                .anyMatch(count -> count > 0);
        boolean pass = failed == 0 && (submittedOrders > 0 || !hadExecutableSelections);
        List<String> lines = List.of(
                "symbol,jforex_execution_parity_pass,submitted_orders,execution_failures",
                csv(
                        symbol,
                        Boolean.toString(pass),
                        Long.toString(submittedOrders),
                        Long.toString(failed)
                )
        );
        writeFile(reportDir.resolve(symbol + "_" + artifactPrefix + "_execution_parity_summary.csv"), lines);
    }

    private static int parsePredictCycleInt(String detail, String key) {
        if (detail == null || detail.isBlank()) {
            return 0;
        }
        String prefix = key + "=";
        for (String part : detail.split(";")) {
            String trimmed = part.trim();
            if (!trimmed.startsWith(prefix)) {
                continue;
            }
            try {
                return Integer.parseInt(trimmed.substring(prefix.length()));
            } catch (NumberFormatException ignored) {
                return 0;
            }
        }
        return 0;
    }

    private void writeLifecycleSummary(String symbol, List<EventRow> rows, Collection<OcoGroupState> groups) {
        long failed = rows.stream().filter(row -> row.category().equals("lifecycle") && !row.pass()).count();
        long violations = groups.stream()
                .filter(group -> symbol.equalsIgnoreCase(group.symbol))
                .filter(group -> group.lifecycleViolation)
                .count();
        boolean pass = failed == 0 && violations == 0;
        List<String> lines = List.of(
                "symbol,execution_lifecycle_pass,lifecycle_failures,lifecycle_violations",
                csv(symbol, Boolean.toString(pass), Long.toString(failed), Long.toString(violations))
        );
        writeFile(reportDir.resolve(symbol + "_" + artifactPrefix + "_execution_lifecycle_summary.csv"), lines);
    }

    private void writeOperationalSummary(String symbol, List<EventRow> rows) {
        Map<String, Boolean> stepStatus = new LinkedHashMap<>();
        for (EventRow row : rows) {
            if (!row.category().equals("operational")) {
                continue;
            }
            stepStatus.put(row.eventName(), row.pass());
        }
        boolean pass = REQUIRED_OPERATIONAL_STEPS.stream().allMatch(step -> Boolean.TRUE.equals(stepStatus.get(step)));
        List<String> lines = List.of(
                "symbol,operational_ready_pass,completed_steps,required_steps",
                csv(
                        symbol,
                        Boolean.toString(pass),
                        Integer.toString((int) stepStatus.entrySet().stream().filter(Map.Entry::getValue).count()),
                        Integer.toString(REQUIRED_OPERATIONAL_STEPS.size())
                )
        );
        writeFile(reportDir.resolve(symbol + "_" + artifactPrefix + "_operational_ready_summary.csv"), lines);
    }

    private void writeFile(Path path, List<String> lines) {
        try {
            Files.write(path, lines, StandardCharsets.UTF_8);
        } catch (IOException exc) {
            throw new IllegalStateException("Failed to write Stage 14 artifact: " + path, exc);
        }
    }

    private static String csv(String... values) {
        List<String> out = new ArrayList<>(values.length);
        for (String value : values) {
            String safe = value == null ? "" : value.replace("\"", "\"\"");
            out.add("\"" + safe + "\"");
        }
        return String.join(",", out);
    }

    private record EventRow(
            Instant eventTs,
            String symbol,
            String category,
            String eventName,
            boolean pass,
            String detail
    ) {
        private static EventRow pass(String symbol, String category, String eventName, String detail) {
            return new EventRow(Instant.now(), symbol, category, eventName, true, detail);
        }

        private static EventRow fail(String symbol, String category, String eventName, String detail) {
            return new EventRow(Instant.now(), symbol, category, eventName, false, detail);
        }
    }
}
