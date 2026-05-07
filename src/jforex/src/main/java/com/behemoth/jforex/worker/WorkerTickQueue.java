package com.behemoth.jforex.worker;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.atomic.AtomicLong;

public final class WorkerTickQueue {
    private final LinkedTransferQueue<TickEvent> queue = new LinkedTransferQueue<>();
    private final AtomicLong pendingCount = new AtomicLong(0);

    public void put(TickEvent event) {
        pendingCount.incrementAndGet();
        queue.put(event);
    }

    public TickEvent take() throws InterruptedException {
        return queue.take();
    }

    public void drainTo(List<TickEvent> target, int maxElements) {
        queue.drainTo(target, maxElements);
    }

    public List<TickEvent> drainAll() {
        List<TickEvent> batch = new ArrayList<>();
        queue.drainTo(batch);
        return batch;
    }

    public void markProcessed(int count) {
        if (count > 0) {
            pendingCount.addAndGet(-count);
        }
    }

    public long pendingCount() {
        return pendingCount.get();
    }

    public void awaitDrained() {
        while (pendingCount.get() > 0) {
            try {
                Thread.sleep(1L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }
}
