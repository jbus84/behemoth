package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class SymbolReadinessRegistryTest {
    @Test
    void registryTransitionsReadyToStaleAndBack() {
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"), 30);
        Instant now = Instant.parse("2026-03-22T12:00:00Z");

        registry.markReady("EURUSD", now, 312, now.minusSeconds(5));
        registry.refreshFreshness(now.plusSeconds(40));
        assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);

        registry.recordFreshTick("EURUSD", now.plusSeconds(41));
        registry.refreshFreshness(now.plusSeconds(42));
        assertThat(registry.snapshot("EURUSD").state()).isEqualTo(SymbolReadinessState.READY);
    }

    @Test
    void liveSnapshotCarriesRegistryManagedMetadataAndCounts() {
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD", "GBPUSD"), 30);
        Instant parquetStart = Instant.parse("2026-03-22T11:50:00Z");
        Instant parquetTail = Instant.parse("2026-03-22T11:59:30Z");
        Instant bridgeStart = Instant.parse("2026-03-22T12:00:00Z");
        Instant bridgeRequestedTo = Instant.parse("2026-03-22T12:29:00Z");
        Instant bridgeEnd = Instant.parse("2026-03-22T12:29:45Z");
        Instant readyAt = Instant.parse("2026-03-22T12:30:00Z");
        Instant asOf = Instant.parse("2026-03-22T12:30:10Z");
        Instant failedAt = Instant.parse("2026-03-22T12:31:00Z");

        registry.markParquetWarming("EURUSD", parquetStart, parquetTail);
        registry.markBridging("EURUSD", bridgeStart);
        registry.recordBridgeProgress("EURUSD", bridgeRequestedTo, bridgeEnd);
        registry.markBridgeComplete("EURUSD", bridgeEnd);
        registry.markReady("EURUSD", readyAt, 312, bridgeEnd);

        registry.markParquetWarming("GBPUSD", parquetStart.minusSeconds(30), parquetTail.minusSeconds(30));
        registry.markStartupTimeoutReached("GBPUSD");
        registry.markErrorPaused("GBPUSD", failedAt, "bridge_timeout");

        LiveReadinessSnapshot live = registry.liveSnapshot(asOf, "jforex_live");

        assertThat(live.sessionTradableSymbolCount()).isEqualTo(1);
        assertThat(live.sessionTotalSymbolCount()).isEqualTo(2);
        assertThat(live.symbols()).hasSize(2);
        assertThat(live.symbols())
                .extracting(SymbolReadinessSnapshot::symbol)
                .containsExactly("EURUSD", "GBPUSD");

        SymbolReadinessSnapshot eurusd = live.symbols().get(0);
        assertThat(eurusd.state()).isEqualTo(SymbolReadinessState.READY);
        assertThat(eurusd.entriesAllowed()).isTrue();
        assertThat(eurusd.parquetTailTsUtc()).isEqualTo(parquetTail);
        assertThat(eurusd.bridgeStartTsUtc()).isEqualTo(bridgeStart);
        assertThat(eurusd.bridgeLastRequestedToUtc()).isEqualTo(bridgeRequestedTo);
        assertThat(eurusd.bridgeEndTsUtc()).isEqualTo(bridgeEnd);
        assertThat(eurusd.lastIngestedTickTsUtc()).isEqualTo(bridgeEnd);
        assertThat(eurusd.stalenessSeconds()).isEqualTo(15L);
        assertThat(eurusd.warmupBarCount100()).isEqualTo(312);
        assertThat(eurusd.startupTimeoutReached()).isFalse();
        assertThat(eurusd.lastFailureReason()).isEmpty();
        assertThat(eurusd.lastStateTransitionUtc()).isEqualTo(readyAt);

        SymbolReadinessSnapshot gbpusd = live.symbols().get(1);
        assertThat(gbpusd.state()).isEqualTo(SymbolReadinessState.ERROR_PAUSED);
        assertThat(gbpusd.entriesAllowed()).isFalse();
        assertThat(gbpusd.parquetTailTsUtc()).isEqualTo(parquetTail.minusSeconds(30));
        assertThat(gbpusd.bridgeStartTsUtc()).isNull();
        assertThat(gbpusd.bridgeLastRequestedToUtc()).isNull();
        assertThat(gbpusd.bridgeEndTsUtc()).isNull();
        assertThat(gbpusd.lastIngestedTickTsUtc()).isNull();
        assertThat(gbpusd.stalenessSeconds()).isZero();
        assertThat(gbpusd.warmupBarCount100()).isZero();
        assertThat(gbpusd.startupTimeoutReached()).isTrue();
        assertThat(gbpusd.lastFailureReason()).isEqualTo("bridge_timeout");
        assertThat(gbpusd.lastStateTransitionUtc()).isEqualTo(failedAt);
    }

    @Test
    void markReadyLeavesSymbolPausedWhenTickIsAlreadyStale() {
        SymbolReadinessRegistry registry = SymbolReadinessRegistry.forSymbols(List.of("EURUSD"), 30);
        Instant transitionTs = Instant.parse("2026-03-22T12:00:00Z");

        registry.markReady("EURUSD", transitionTs, 312, transitionTs.minusSeconds(31));

        SymbolReadinessSnapshot snapshot = registry.snapshot("EURUSD");
        assertThat(snapshot.state()).isEqualTo(SymbolReadinessState.STALE_PAUSED);
        assertThat(snapshot.entriesAllowed()).isFalse();
        assertThat(snapshot.stalenessSeconds()).isEqualTo(31);
    }
}
