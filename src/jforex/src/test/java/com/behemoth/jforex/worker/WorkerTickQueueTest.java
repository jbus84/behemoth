package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class WorkerTickQueueTest {
    @Test
    void tracksPendingCountAcrossDrainBatches() throws Exception {
        WorkerTickQueue queue = new WorkerTickQueue();
        queue.put(new TickEvent(1L, 1.1, 1.1002, 10L));
        queue.put(new TickEvent(2L, 1.2, 1.2002, 20L));

        TickEvent first = queue.take();
        List<TickEvent> rest = new ArrayList<>();
        queue.drainTo(rest, 10);

        assertThat(first.epochMs()).isEqualTo(1L);
        assertThat(rest).hasSize(1);
        assertThat(queue.pendingCount()).isEqualTo(2L);

        queue.markProcessed(2);

        assertThat(queue.pendingCount()).isZero();
    }
}
