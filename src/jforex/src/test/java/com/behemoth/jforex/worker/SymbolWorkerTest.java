package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.core.RuntimeTick;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.Test;

class SymbolWorkerTest {

    @Test
    void enqueueAndDrainProcessesAllTicks() throws InterruptedException {
        CopyOnWriteArrayList<RuntimeTick> received = new CopyOnWriteArrayList<>();
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> {
            assertThat(symbol).isEqualTo("EURUSD");
            received.addAll(ticks);
        });

        worker.start();

        Instant t1 = Instant.parse("2025-01-01T00:00:00Z");
        Instant t2 = Instant.parse("2025-01-01T00:00:01Z");
        worker.enqueue(new RuntimeTick("EURUSD", t1, 1.1000, 1.1002));
        worker.enqueue(new RuntimeTick("EURUSD", t2, 1.1001, 1.1003));

        worker.drain();
        worker.stop();

        assertThat(received).hasSize(2);
        assertThat(received.get(0).bid()).isEqualTo(1.1000);
        assertThat(received.get(1).bid()).isEqualTo(1.1001);
    }

    @Test
    void preservesTickOrdering() throws InterruptedException {
        CopyOnWriteArrayList<RuntimeTick> received = new CopyOnWriteArrayList<>();
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> received.addAll(ticks));

        worker.start();

        for (int i = 0; i < 100; i++) {
            worker.enqueue(
                    new RuntimeTick(
                            "EURUSD",
                            Instant.now(),
                            1.1000 + i * 0.0001,
                            1.1002 + i * 0.0001));
        }

        worker.drain();
        worker.stop();

        assertThat(received).hasSize(100);
        for (int i = 0; i < 100; i++) {
            assertThat(received.get(i).bid()).isEqualTo(1.1000 + i * 0.0001);
        }
    }

    @Test
    void drainReturnsImmediatelyWhenQueueEmpty() throws InterruptedException {
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> {});
        worker.start();

        long start = System.currentTimeMillis();
        worker.drain();
        long elapsed = System.currentTimeMillis() - start;

        worker.stop();

        assertThat(elapsed).isLessThan(100);
    }

    @Test
    void stopInterruptsWorker() throws InterruptedException {
        CopyOnWriteArrayList<RuntimeTick> received = new CopyOnWriteArrayList<>();
        SymbolWorker worker = new SymbolWorker("EURUSD", (symbol, ticks) -> received.addAll(ticks));

        worker.start();

        worker.enqueue(new RuntimeTick("EURUSD", Instant.now(), 1.1000, 1.1002));
        Thread.sleep(50);
        worker.stop();

        assertThat(received).hasSize(1);
        assertThat(received.get(0).bid()).isEqualTo(1.1000);
    }
}
