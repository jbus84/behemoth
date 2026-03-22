package com.behemoth.jforex.live;

import static org.assertj.core.api.Assertions.assertThat;

import com.behemoth.jforex.config.JForexSessionConfig;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class LiveReadinessCoordinatorTest {
    private static final String LIVE_PREFIX = "BEHEMOTH_JFOREX_LIVE_";
    private static final Map<String, String> ORIGINAL_LIVE_PROPERTIES = new HashMap<>();

    @BeforeAll
    static void setUpSessionConfigProperties() {
        snapshotAndClearLiveProperties();
    }

    @AfterAll
    static void restoreSessionConfigProperties() {
        ORIGINAL_LIVE_PROPERTIES.forEach((key, value) -> {
            if (value == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, value);
            }
        });
    }

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
        Map<String, String> environment = new HashMap<>(System.getenv());
        environment.keySet().removeIf(key -> key.startsWith(LIVE_PREFIX));
        environment.put("BEHEMOTH_JFOREX_JNLP_URI", "http://127.0.0.1/test.jnlp");
        environment.put("BEHEMOTH_JFOREX_USERNAME", "user");
        environment.put("BEHEMOTH_JFOREX_PASSWORD", "pass");
        return Collections.unmodifiableMap(environment);
    }

    private static void snapshotAndClearLiveProperties() {
        System.getProperties().stringPropertyNames().stream()
                .filter(key -> key.startsWith(LIVE_PREFIX))
                .forEach(key -> {
                    ORIGINAL_LIVE_PROPERTIES.put(key, System.getProperty(key));
                    System.clearProperty(key);
                });
    }
}
