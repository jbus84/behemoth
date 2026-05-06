package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Connects to Dukascopy, snapshots current broker orders, then exits.
 */
public final class JForexBrokerSnapshotRunner {
    private static final int CONNECT_TIMEOUT_SECONDS = 120;
    private static final Duration SNAPSHOT_TIMEOUT = Duration.ofSeconds(30);

    private JForexBrokerSnapshotRunner() {
    }

    public static void main(String[] args) throws Exception {
        JForexSessionConfig config = JForexSessionConfig.fromEnvironment(false);
        Path snapshotPath = resolveSnapshotPath(config);
        CountDownLatch completed = new CountDownLatch(1);
        IClient client = ClientFactory.getDefaultInstance();
        try {
            JForexLiveRunner.startWhenConnected(
                    new DukascopySnapshotClient(client, config),
                    new BrokerSnapshotStrategy(
                            new BrokerOrderSnapshotWriter(snapshotPath, buildObjectMapper()),
                            completed
                    ),
                    CONNECT_TIMEOUT_SECONDS,
                    Thread::sleep
            );
            if (!completed.await(SNAPSHOT_TIMEOUT.toSeconds(), TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for broker snapshot strategy to stop");
            }
        } finally {
            if (client.isConnected()) {
                client.disconnect();
            }
        }
        System.exit(0);
    }

    private static Path resolveSnapshotPath(JForexSessionConfig config) {
        String raw = Objects.requireNonNullElse(
                System.getenv("BEHEMOTH_JFOREX_BROKER_SNAPSHOT_PATH"),
                ""
        ).trim();
        if (!raw.isEmpty()) {
            return Path.of(raw);
        }
        return config.reportDir().resolve("runtime").resolve("live_broker_snapshot.json");
    }

    private static ObjectMapper buildObjectMapper() {
        return new ObjectMapper()
                .registerModule(new JavaTimeModule())
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    private record DukascopySnapshotClient(IClient client, JForexSessionConfig config)
            implements JForexLiveRunner.LiveClient {
        @Override
        public void connect() throws Exception {
            client.connect(config.jnlpUri().toString(), config.username(), config.password());
        }

        @Override
        public boolean isConnected() {
            return client.isConnected();
        }

        @Override
        public void startStrategy(com.dukascopy.api.IStrategy strategy) throws Exception {
            client.startStrategy(strategy);
        }
    }
}
