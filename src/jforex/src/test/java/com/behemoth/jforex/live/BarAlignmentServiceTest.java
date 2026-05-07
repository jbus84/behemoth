package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

final class BarAlignmentServiceTest {
    @Test
    void warmupKeepTickCountPreservesConfiguredBarPhase() {
        BarAlignmentService service = new BarAlignmentService();

        int keep = service.warmupKeepTickCount(12_345, 5_000, 100);

        assertThat(keep).isEqualTo(5_045);
        assertThat((12_345 - keep) % 100).isZero();
    }
}
