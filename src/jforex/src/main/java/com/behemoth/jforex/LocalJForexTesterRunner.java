package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.BehemothStrategyCore;
import com.behemoth.jforex.core.RuntimeInstrument;
import com.behemoth.jforex.local.LocalExecutionPort;
import com.behemoth.jforex.local.LocalJForexHarnessConfig;
import com.behemoth.jforex.local.ParquetTickLoader;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.BackfillRequestPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.state.ExecutionStateStore;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Local JForex-like surrogate harness that reuses the Java strategy core against parquet ticks.
 */
public final class LocalJForexTesterRunner {
    private LocalJForexTesterRunner() {
    }

    public static void main(String[] args) {
        LocalJForexHarnessConfig harnessConfig = LocalJForexHarnessConfig.fromEnvironment();
        JForexSessionConfig sessionConfig = harnessConfig.toSessionConfig();
        PythonPredictionClient predictionClient = new PythonPredictionClient(
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build(),
                sessionConfig.apiBaseUri(),
                Duration.ofSeconds(sessionConfig.apiTimeoutSeconds())
        );
        JForexMetrics metrics = JForexMetrics.start(sessionConfig);
        Path runtimeDir = sessionConfig.reportDir().resolve("runtime");
        Path statePath = runtimeDir.resolve(safeFileComponent(sessionConfig.runId()) + "_active_oco_state.json");
        try {
            Files.createDirectories(runtimeDir);
            Files.deleteIfExists(statePath);
        } catch (Exception exc) {
            throw new IllegalStateException("Failed to prepare local JForex state path: " + statePath, exc);
        }
        ExecutionStateStore stateStore = new ExecutionStateStore(statePath, predictionClient.objectMapper());
        Stage14ArtifactWriter artifactWriter = new Stage14ArtifactWriter(sessionConfig.reportDir(), "local_jforex");
        LocalExecutionPort executionPort = new LocalExecutionPort();
        BehemothStrategyCore core = new BehemothStrategyCore(
                sessionConfig,
                predictionClient,
                stateStore,
                artifactWriter,
                metrics,
                executionPort
        );
        executionPort.setEventListener(core::onOrderEvent);

        Map<String, ParquetTickLoader.TickWindow> windows = new LinkedHashMap<>();
        List<RuntimeInstrument> instruments = new ArrayList<>();
        ParquetTickLoader loader = new ParquetTickLoader();
        for (String rawSymbol : harnessConfig.instruments()) {
            String symbol = normalizeSymbol(rawSymbol);
            ParquetTickLoader.TickWindow window = loader.load(harnessConfig, symbol);
            windows.put(symbol, window);
            instruments.add(new RuntimeInstrument(symbol, pipSize(symbol)));
        }

        try {
            for (Map.Entry<String, ParquetTickLoader.TickWindow> entry : windows.entrySet()) {
                backfillWarmup(predictionClient, sessionConfig, harnessConfig.barAlignTicks(), entry.getKey(), entry.getValue().warmup());
            }
            core.start(instruments);
            core.onAccountSnapshot(harnessConfig.startingBalance(), harnessConfig.startingBalance(), harnessConfig.startUtc());

            List<com.behemoth.jforex.core.RuntimeTick> merged = windows.values().stream()
                    .flatMap(window -> window.stream().stream())
                    .sorted(Comparator.comparing(com.behemoth.jforex.core.RuntimeTick::timestamp).thenComparing(com.behemoth.jforex.core.RuntimeTick::symbol))
                    .toList();
            for (com.behemoth.jforex.core.RuntimeTick tick : merged) {
                executionPort.onTick(tick);
                core.onTick(tick);
                core.drainWorker(tick.symbol());
            }
            for (String symbol : windows.keySet()) {
                core.flushSymbol(symbol);
            }
            executionPort.closeOpenOrdersAtEnd();
            core.onAccountSnapshot(harnessConfig.startingBalance(), harnessConfig.startingBalance(), harnessConfig.endUtc());
            core.stop();
        } finally {
            metrics.close();
        }
    }

    private static void backfillWarmup(
            PythonPredictionClient predictionClient,
            JForexSessionConfig sessionConfig,
            int barTicks,
            String symbol,
            List<com.behemoth.jforex.core.RuntimeTick> warmup
    ) {
        if (warmup.isEmpty()) {
            return;
        }
        List<IncomingTickPayload> ticks = new ArrayList<>(warmup.size());
        long seq = 1L;
        for (com.behemoth.jforex.core.RuntimeTick tick : warmup) {
            ticks.add(new IncomingTickPayload(
                    symbol,
                    tick.timestamp(),
                    tick.bid(),
                    tick.ask(),
                    1.0,
                    seq++,
                    sessionConfig.runId()
            ));
        }
        predictionClient.backfill(new BackfillRequestPayload(symbol, barTicks, ticks, sessionConfig.runId()));
    }

    private static double pipSize(String symbol) {
        return symbol.endsWith("JPY") ? 0.01 : 0.0001;
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }

    private static String safeFileComponent(String raw) {
        String txt = String.valueOf(raw == null ? "" : raw).trim().toLowerCase();
        if (txt.isEmpty()) {
            return "local_jforex_surrogate";
        }
        return txt.replaceAll("[^a-z0-9._-]+", "_");
    }
}
