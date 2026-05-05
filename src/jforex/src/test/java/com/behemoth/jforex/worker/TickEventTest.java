package com.behemoth.jforex.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class TickEventTest {

    @Test
    void createsValidTickEvent() {
        Instant now = Instant.parse("2025-01-01T00:00:00Z");
        long epochMs = now.toEpochMilli();
        TickEvent event = new TickEvent(epochMs, 1.1000, 1.1002, 123456789L);

        assertThat(event.epochMs()).isEqualTo(epochMs);
        assertThat(event.bid()).isEqualTo(1.1000);
        assertThat(event.ask()).isEqualTo(1.1002);
        assertThat(event.receiveTimeNs()).isEqualTo(123456789L);
        assertThat(event.timestamp()).isEqualTo(now);
    }

    @Test
    void rejectsInvalidBidAsk() {
        assertThatThrownBy(() -> new TickEvent(System.currentTimeMillis(), 1.1002, 1.1000, 0L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("ask");
    }

    @Test
    void rejectsNegativePrices() {
        assertThatThrownBy(() -> new TickEvent(System.currentTimeMillis(), -1.0, 1.1002, 0L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("bid");
    }
}
