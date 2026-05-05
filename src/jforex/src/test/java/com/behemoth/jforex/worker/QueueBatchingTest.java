package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.core.RuntimeTick;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;

class QueueBatchingTest {

    @Test
    void largeEnqueueCreatesBatches() throws InterruptedException {
        CopyOnWriteArrayList<Integer> batchSizes = new CopyOnWriteArrayList<>();
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> batchSizes.add(ticks.size()));

        worker.start();

        for (int i = 0; i < 5000; i++) {
            worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
        }

        worker.drain();
        worker.stop();

        assertThat(batchSizes).hasSizeGreaterThanOrEqualTo(3);
        int total = batchSizes.stream().mapToInt(Integer::intValue).sum();
        assertThat(total).isEqualTo(5000);
    }

    @Test
    void noTicksAreDropped() throws InterruptedException {
        CopyOnWriteArrayList<RuntimeTick> received = new CopyOnWriteArrayList<>();
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> received.addAll(ticks));

        worker.start();

        for (int i = 0; i < 10000; i++) {
            worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
        }

        worker.drain();
        worker.stop();

        assertThat(received).hasSize(10000);
    }
}
