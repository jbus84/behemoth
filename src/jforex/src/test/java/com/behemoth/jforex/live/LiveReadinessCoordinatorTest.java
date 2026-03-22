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

    private static Map<String, String> testEnvironment() {
        Map<String, String> environment = new HashMap<>();
        environment.put("BEHEMOTH_JFOREX_JNLP_URI", "http://127.0.0.1/test.jnlp");
        environment.put("BEHEMOTH_JFOREX_USERNAME", "user");
        environment.put("BEHEMOTH_JFOREX_PASSWORD", "pass");
        return Map.copyOf(environment);
    }
}
