package com.behemoth.jforex.worker;

import com.behemoth.jforex.core.RuntimeTick;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class SymbolWorker {
    private static final int MAX_BATCH = 2000;

    private final String symbol;
    private final TickProcessor processor;
    private final LinkedTransferQueue<TickEvent> queue = new LinkedTransferQueue<>();
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicLong pendingCount = new AtomicLong(0);
    private Thread thread;

    public SymbolWorker(String symbol, TickProcessor processor) {
        this.symbol = symbol;
        this.processor = processor;
    }

    @FunctionalInterface
    public interface TickProcessor {
        void process(String symbol, List<RuntimeTick> ticks);
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

    private void runLoop() {
        while (running.get()) {
            List<TickEvent> batch = new ArrayList<>(MAX_BATCH);
            try {
                TickEvent first = queue.take();
                batch.add(first);
                queue.drainTo(batch, MAX_BATCH - 1);
                processBatch(batch);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                e.printStackTrace();
            } finally {
                if (!batch.isEmpty()) {
                    pendingCount.addAndGet(-batch.size());
                }
            }
        }
    }

    private void processBatch(List<TickEvent> batch) {
        List<RuntimeTick> ticks = new ArrayList<>(batch.size());
        for (TickEvent event : batch) {
            ticks.add(new RuntimeTick(symbol, event.timestamp(), event.bid(), event.ask()));
        }
        processor.process(symbol, ticks);
    }
}
