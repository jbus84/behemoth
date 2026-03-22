package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class SymbolReadinessRegistryTest {
    @Test
    void registryTransitionsReadyToStaleAndBack() {
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"));
        Instant now = Instant.parse("2026-03-22T12:00:00Z");

        registry.markReady("EURUSD", now, 312, now.minusSeconds(5));
        registry.refreshFreshness(now.plusSeconds(40), 30);
        assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);

        registry.recordFreshTick("EURUSD", now.plusSeconds(41));
        registry.refreshFreshness(now.plusSeconds(42), 30);
        assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
    }
}
