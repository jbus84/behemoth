package com.behemoth.jforex.worker;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.core.RuntimeTick;
import com.behemoth.jforex.observability.JForexMetrics;
import com.behemoth.jforex.reporting.Stage14ArtifactWriter;
import com.behemoth.jforex.runtime.PythonApiException;
import com.behemoth.jforex.runtime.PythonPredictionClient;
import com.behemoth.jforex.runtime.dto.BarrierActionPayload;
import com.behemoth.jforex.runtime.dto.IncomingTickPayload;
import com.behemoth.jforex.runtime.dto.PredictRequestPayload;
import com.behemoth.jforex.runtime.dto.PredictResponsePayload;
import com.behemoth.jforex.runtime.dto.PredictionResponseItem;
import com.behemoth.jforex.runtime.dto.TickBatchRequestPayload;
import com.behemoth.jforex.runtime.dto.TickBatchResponsePayload;
import com.behemoth.jforex.runtime.dto.TickIngestResponsePayload;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class SymbolWorker {
    private static final int MAX_BATCH = 2000;
    private static final int MAX_TICK_BATCH_TIMEOUT_RETRIES = 2;
    private static final long TICK_BATCH_RETRY_BACKOFF_MS = 250L;
    private static final double FX_UNITS_PER_MILLION = 1_000_000.0;

    private final String symbol;
    private final JForexSessionConfig sessionConfig;
    private final PythonPredictionClient predictionClient;
    private final JForexMetrics metrics;
    private final Stage14ArtifactWriter artifactWriter;
    private final ActionCallbacks callbacks;
    private final LinkedTransferQueue<TickEvent> queue = new LinkedTransferQueue<>();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicLong pendingCount = new AtomicLong(0);
    private Thread thread;

    private final List<IncomingTickPayload> pendingTicks = new ArrayList<>();
    private long nextClientTickSeq = 1L;
    private final Map<Integer, Long> barOrdinalsByBarTicks = new LinkedHashMap<>();
    private RuntimeTick lastTick;

    public SymbolWorker(
            String symbol,
            JForexSessionConfig sessionConfig,
            PythonPredictionClient predictionClient,
            JForexMetrics metrics,
            Stage14ArtifactWriter artifactWriter,
            ActionCallbacks callbacks
    ) {
        this.symbol = symbol;
        this.sessionConfig = sessionConfig;
        this.predictionClient = predictionClient;
        this.metrics = metrics;
        this.artifactWriter = artifactWriter;
        this.callbacks = callbacks;
    }

    public interface ActionCallbacks {
        boolean entriesAllowed(String symbol);
        void submitMarketOrder(String symbol, String label, String side, double amountMillions,
                               String scanId, String candidateUid, String reservationId, int horizon,
                               Instant now);
        void closePositionByScanId(String symbol, String scanId, Instant now);
    }

    public void start() {
        if (running.compareAndSet(false, true)) {
            thread = new Thread(this::runLoop, "behemoth-worker-" + symbol);
            thread.start();
        }
    }

    public void stop() {
        running.set(false);
        if (thread != null) {
            thread.interrupt();
            try {
                thread.join(5000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        List<TickEvent> batch = new ArrayList<>();
        queue.drainTo(batch);
        if (!batch.isEmpty()) {
            try {
                processBatch(batch);
            } catch (Exception e) {
                metrics.recordWorkerFatal(symbol);
                artifactWriter.markOperationalStep(symbol, "worker_fatal", false, e.getMessage());
            } finally {
                pendingCount.addAndGet(-batch.size());
            }
        }
        if (!pendingTicks.isEmpty()) {
            try {
                flushPendingTicks();
            } catch (Exception e) {
                metrics.recordWorkerFatal(symbol);
                artifactWriter.markOperationalStep(symbol, "worker_fatal", false, e.getMessage());
            }
        }
    }

    public void enqueue(RuntimeTick tick) {
        pendingCount.incrementAndGet();
        queue.put(new TickEvent(tick.timestamp().toEpochMilli(), tick.bid(), tick.ask(), System.nanoTime()));
    }

    public void drain() {
        while (pendingCount.get() > 0) {
            try {
                Thread.sleep(1L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    public void seedClientTickSeq(long lastClientTickSeq) {
        this.nextClientTickSeq = lastClientTickSeq + 1L;
    }

    public long pendingCount() {
        return pendingCount.get();
    }

    private void runLoop() {
        while (running.get()) {
            List<TickEvent> batch = new ArrayList<>(MAX_BATCH);
            try {
                TickEvent first = queue.take();
                batch.add(first);
                queue.drainTo(batch, MAX_BATCH - 1);

                long startNs = System.nanoTime();
                long oldestReceiveTimeNs = batch.stream().mapToLong(TickEvent::receiveTimeNs).min().orElse(0L);
                long queueAgeMs = oldestReceiveTimeNs > 0L ? (System.nanoTime() - oldestReceiveTimeNs) / 1_000_000L : 0L;

                processBatch(batch);

                long durationMs = (System.nanoTime() - startNs) / 1_000_000L;
                metrics.recordWorkerDrainDurationMs(symbol, durationMs);
                metrics.recordWorkerBatchSize(symbol, batch.size());
                if (queueAgeMs > 0L) {
                    metrics.recordWorkerQueueAgeMs(symbol, queueAgeMs);
                }
                if (queueAgeMs > 50L) {
                    artifactWriter.markOperationalStep(symbol, "worker_queue_age_high", false,
                            "queueAgeMs=" + queueAgeMs);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                metrics.recordWorkerFatal(symbol);
                artifactWriter.markOperationalStep(symbol, "worker_fatal", false, e.getMessage());
            } finally {
                if (!batch.isEmpty()) {
                    pendingCount.addAndGet(-batch.size());
                }
            }
        }
    }

    private void processBatch(List<TickEvent> batch) {
        for (TickEvent event : batch) {
            pendingTicks.add(new IncomingTickPayload(
                    symbol,
                    event.timestamp(),
                    event.bid(),
                    event.ask(),
                    1.0,
                    nextClientTickSeq++,
                    sessionConfig.runId()
            ));
            lastTick = new RuntimeTick(symbol, event.timestamp(), event.bid(), event.ask());
            metrics.recordTicksReceived(symbol, 1);
            if (pendingTicks.size() >= sessionConfig.tickBatchSize()) {
                flushPendingTicks();
            }
        }
    }

    private void flushPendingTicks() {
        if (pendingTicks.isEmpty()) {
            return;
        }
        List<IncomingTickPayload> payload = List.copyOf(pendingTicks);
        pendingTicks.clear();
        TickBatchRequestPayload request = new TickBatchRequestPayload(
                symbol,
                payload,
                sessionConfig.runId()
        );
        int attempt = 0;
        while (true) {
            try {
                try (JForexMetrics.TimerContext ignored = metrics.startWorkerHttpTicksTimer(symbol)) {
                    TickBatchResponsePayload response = predictionClient.tickBatch(request);
                    metrics.recordTickBatch(symbol, response.acceptedCount(), response.droppedCount());
                    artifactWriter.markOperationalStep(
                            symbol,
                            "feed_status",
                            true,
                            "accepted=" + response.acceptedCount() + ";attempt=" + (attempt + 1)
                    );
                    if (response.barCompleted() && response.completedBarTicks() != null && !response.completedBarTicks().isEmpty()) {
                        triggerPrediction(response.completedBarTicks());
                    }
                }
                return;
            } catch (RuntimeException exc) {
                if (isRetriableTickBatchFailure(exc) && attempt < MAX_TICK_BATCH_TIMEOUT_RETRIES) {
                    attempt += 1;
                    sleepBeforeRetry();
                    continue;
                }
                if (isRetriableTickBatchFailure(exc)) {
                    TickIngestAggregate aggregate = ingestTicksIndividually(payload);
                    metrics.recordTickBatch(symbol, aggregate.acceptedCount(), aggregate.droppedCount());
                    artifactWriter.markOperationalStep(
                            symbol,
                            "feed_status",
                            true,
                            "accepted=" + aggregate.acceptedCount() + ";mode=single_tick_fallback"
                    );
                    if (!aggregate.completedBarTicks().isEmpty()) {
                        triggerPrediction(aggregate.completedBarTicks());
                    }
                    return;
                }
                pendingTicks.addAll(0, payload);
                artifactWriter.markOperationalStep(symbol, "feed_status", false, exc.getMessage());
                throw exc;
            }
        }
    }

    private void triggerPrediction(List<Integer> completedBarTicks) {
        for (int barTick : completedBarTicks) {
            barOrdinalsByBarTicks.compute(barTick, (k, v) -> v == null ? 0L : v + 1L);
        }
        Map<Integer, Long> barOrdinals = Map.copyOf(barOrdinalsByBarTicks);

        try (JForexMetrics.TimerContext predictTimer = metrics.startPredictTimer(symbol);
             JForexMetrics.TimerContext workerTimer = metrics.startWorkerHttpPredictTimer(symbol)) {
            PredictResponsePayload response = predictionClient.predict(new PredictRequestPayload(
                    symbol,
                    sessionConfig.riskEnabled(),
                    sessionConfig.requestedVolumeUnits(),
                    completedBarTicks,
                    sessionConfig.runId(),
                    barOrdinals
            ));
            if (lastTick != null) {
                long tickToPredictMs = System.currentTimeMillis() - lastTick.timestamp().toEpochMilli();
                if (tickToPredictMs > 0L) {
                    metrics.recordWorkerTickToPredictMs(symbol, tickToPredictMs);
                }
            }
            List<PredictionResponseItem> predictions = response.predictions();

            int pythonSelected = 0;
            for (PredictionResponseItem p : predictions) {
                if (p.isSelected()) pythonSelected++;
            }
            Instant predictCloseTs = predictions.stream()
                    .map(PredictionResponseItem::closeTs)
                    .filter(Objects::nonNull)
                    .findFirst()
                    .orElseGet(() -> lastTick != null ? lastTick.timestamp() : Instant.now());
            metrics.recordSelectedPredictions(symbol, pythonSelected, 0);
            artifactWriter.recordPredictCycle(
                    symbol,
                    predictCloseTs,
                    predictions.size(),
                    pythonSelected,
                    response.actions().size(),
                    0,
                    List.of(),
                    completedBarTicks
            );

            executeActions(response.actions());
        } catch (PythonApiException exc) {
            if (exc.statusCode() == 422 && exc.detail().contains("Insufficient warmup bars")) {
                metrics.recordPredictWarmup(symbol);
                return;
            }
            metrics.recordPredictFailure(symbol);
            artifactWriter.recordPredictFailure(symbol, exc.detail());
        }
    }

    private void executeActions(List<BarrierActionPayload> actions) {
        double amountMillions = sessionConfig.requestedVolumeUnits() / FX_UNITS_PER_MILLION;
        Instant now = lastTick != null ? lastTick.timestamp() : Instant.now();
        for (BarrierActionPayload action : actions) {
            if (action.isOpenMarket()) {
                if (!sessionConfig.newEntriesEnabled() || !callbacks.entriesAllowed(symbol)) {
                    metrics.recordEntryBlocked(symbol);
                    artifactWriter.markOperationalStep(
                            action.symbol(),
                            "entry_blocked_not_ready",
                            false,
                            sessionConfig.newEntriesEnabled()
                                    ? "entries not allowed in current readiness state"
                                    : "new entries disabled by restart eligibility"
                    );
                    continue;
                }
                String label = "BM_" + action.scanId() + "_" + action.side();
                callbacks.submitMarketOrder(
                        action.symbol(),
                        label,
                        action.side(),
                        amountMillions,
                        action.scanId(),
                        action.candidateUid(),
                        action.reservationId(),
                        action.horizon(),
                        now
                );
            } else if (action.isCloseMarket()) {
                callbacks.closePositionByScanId(action.symbol(), action.scanId(), now);
            }
        }
    }

    private TickIngestAggregate ingestTicksIndividually(List<IncomingTickPayload> payload) {
        int accepted = 0;
        int dropped = 0;
        Set<Integer> completedBarTicks = new LinkedHashSet<>();
        for (int i = 0; i < payload.size(); i++) {
            IncomingTickPayload tick = payload.get(i);
            try {
                TickIngestResponsePayload response = predictionClient.tick(tick);
                if (response.tickAccepted()) {
                    accepted += 1;
                } else {
                    dropped += 1;
                }
                if (response.barCompleted() && response.completedBarTicks() != null) {
                    completedBarTicks.addAll(response.completedBarTicks());
                }
            } catch (RuntimeException exc) {
                pendingTicks.addAll(0, payload.subList(i, payload.size()));
                artifactWriter.markOperationalStep(symbol, "feed_status", false, exc.getMessage());
                throw exc;
            }
        }
        return new TickIngestAggregate(accepted, dropped, List.copyOf(completedBarTicks));
    }

    private static boolean isRetriableTickBatchFailure(RuntimeException exc) {
        if (!(exc instanceof PythonApiException apiException)) {
            return false;
        }
        if (apiException.statusCode() != 599) {
            return false;
        }
        String detail = String.valueOf(apiException.detail()).toLowerCase();
        return detail.contains("timed out") || detail.contains("timeout");
    }

    private static void sleepBeforeRetry() {
        try {
            Thread.sleep(TICK_BATCH_RETRY_BACKOFF_MS);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while retrying tick batch", exc);
        }
    }

    private record TickIngestAggregate(
            int acceptedCount,
            int droppedCount,
            List<Integer> completedBarTicks
    ) {
    }
}
