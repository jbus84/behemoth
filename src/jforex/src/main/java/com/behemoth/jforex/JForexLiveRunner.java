package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;

/**
 * Demo/live session bootstrapper for the JForex adapter.
 */
public final class JForexLiveRunner {
    private static final int CONNECT_TIMEOUT_SECONDS = 120;

    private JForexLiveRunner() {
    }

    public static void main(String[] args) throws Exception {
        JForexSessionConfig config = JForexSessionConfig.fromEnvironment(false);
        JForexMetrics metrics = JForexMetrics.start(config);
        Runtime.getRuntime().addShutdownHook(new Thread(metrics::close));

        IClient client = ClientFactory.getDefaultInstance();
        startWhenConnected(
                new DukascopyLiveClient(client, config),
                new BehemothJForexStrategy(config, metrics),
                CONNECT_TIMEOUT_SECONDS,
                Thread::sleep
        );
    }

    static void startWhenConnected(LiveClient client, IStrategy strategy, int timeoutSeconds, Sleeper sleeper) throws Exception {
        client.connect();
        for (int attempt = 0; attempt < timeoutSeconds; attempt++) {
            if (client.isConnected()) {
                client.startStrategy(strategy);
                return;
            }
            sleeper.sleep(1000L);
        }
        throw new IllegalStateException("Failed to connect to Dukascopy within " + timeoutSeconds + " seconds");
    }

    interface LiveClient {
        void connect() throws Exception;

        boolean isConnected();

        void startStrategy(IStrategy strategy) throws Exception;
    }

    @FunctionalInterface
    interface Sleeper {
        void sleep(long millis) throws InterruptedException;
    }

    private record DukascopyLiveClient(IClient client, JForexSessionConfig config) implements LiveClient {
        @Override
        public void connect() throws Exception {
            client.connect(config.jnlpUri().toString(), config.username(), config.password());
        }

        @Override
        public boolean isConnected() {
            return client.isConnected();
        }

        @Override
        public void startStrategy(IStrategy strategy) throws Exception {
            client.startStrategy(strategy);
        }
    }
}
