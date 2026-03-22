package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class LiveReadinessCoordinatorTest {
    @Test
    void sessionConfigExposesLiveReadinessDefaults() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false, testEnvironment());
        assertThat(cfg.liveReadinessEnabled()).isTrue();
        assertThat(cfg.liveWarmupTicks()).isEqualTo(30_000);
        assertThat(cfg.liveLookbackDays()).isEqualTo(31);
        assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(60);
        assertThat(cfg.liveFreshnessSeconds()).isEqualTo(30);
        assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(20);
    }

    @Test
    void sessionConfigParsesExplicitLiveReadinessOverrides() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false, testEnvironmentWithLiveOverrides());
        assertThat(cfg.liveReadinessEnabled()).isFalse();
        assertThat(cfg.liveWarmupTicks()).isEqualTo(12_345);
        assertThat(cfg.liveLookbackDays()).isEqualTo(7);
        assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(15);
        assertThat(cfg.liveFreshnessSeconds()).isEqualTo(45);
        assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(9);
    }

    private static Map<String, String> testEnvironment() {
        Map<String, String> environment = new HashMap<>();
        environment.put("BEHEMOTH_JFOREX_JNLP_URI", "http://127.0.0.1/test.jnlp");
        environment.put("BEHEMOTH_JFOREX_USERNAME", "user");
        environment.put("BEHEMOTH_JFOREX_PASSWORD", "pass");
        return Map.copyOf(environment);
    }

    private static Map<String, String> testEnvironmentWithLiveOverrides() {
        Map<String, String> environment = new HashMap<>(testEnvironment());
        environment.put("BEHEMOTH_JFOREX_LIVE_READINESS_ENABLED", "false");
        environment.put("BEHEMOTH_JFOREX_LIVE_WARMUP_TICKS", "12345");
        environment.put("BEHEMOTH_JFOREX_LIVE_LOOKBACK_DAYS", "7");
        environment.put("BEHEMOTH_JFOREX_LIVE_BRIDGE_WINDOW_MINUTES", "15");
        environment.put("BEHEMOTH_JFOREX_LIVE_FRESHNESS_SECONDS", "45");
        environment.put("BEHEMOTH_JFOREX_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES", "9");
        return Map.copyOf(environment);
    }
}
