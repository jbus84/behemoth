package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;

/**
 * Demo/live session bootstrapper for the JForex adapter.
 */
public final class JForexLiveRunner {
    private JForexLiveRunner() {
    }

    public static void main(String[] args) throws Exception {
        JForexSessionConfig config = JForexSessionConfig.fromEnvironment(false);
        JForexMetrics metrics = JForexMetrics.start(config);
        Runtime.getRuntime().addShutdownHook(new Thread(metrics::close));

        IClient client = ClientFactory.getDefaultInstance();
        client.connect(config.jnlpUri().toString(), config.username(), config.password());
        client.startStrategy(new BehemothJForexStrategy(config, metrics));
    }
}
