package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class LiveReadinessCoordinatorTest {
    private static final Map<String, String> ORIGINAL_PROPERTIES = new HashMap<>();

    @BeforeAll
    static void setUpSessionConfigProperties() {
        setProperty("BEHEMOTH_JFOREX_JNLP_URI", "http://127.0.0.1/test.jnlp");
        setProperty("BEHEMOTH_JFOREX_USERNAME", "user");
        setProperty("BEHEMOTH_JFOREX_PASSWORD", "pass");
    }

    @AfterAll
    static void restoreSessionConfigProperties() {
        ORIGINAL_PROPERTIES.forEach((key, value) -> {
            if (value == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, value);
            }
        });
    }

    @Test
    void sessionConfigExposesLiveReadinessDefaults() {
        JForexSessionConfig cfg = JForexSessionConfig.fromEnvironment(false);
        assertThat(cfg.liveReadinessEnabled()).isTrue();
        assertThat(cfg.liveWarmupTicks()).isEqualTo(30_000);
        assertThat(cfg.liveLookbackDays()).isEqualTo(31);
        assertThat(cfg.liveBridgeWindowMinutes()).isEqualTo(60);
        assertThat(cfg.liveFreshnessSeconds()).isEqualTo(30);
        assertThat(cfg.liveStartupBridgeTimeoutMinutes()).isEqualTo(20);
    }

    private static void setProperty(String key, String value) {
        ORIGINAL_PROPERTIES.put(key, System.getProperty(key));
        System.setProperty(key, value);
    }
}
