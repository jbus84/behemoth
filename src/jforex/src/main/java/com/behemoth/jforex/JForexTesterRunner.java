package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.behemoth.jforex.observability.JForexMetrics;
import com.dukascopy.api.system.ITesterClient;
import com.dukascopy.api.system.TesterFactory;

/**
 * Deterministic historical certification entrypoint for Stage 14.
 */
public final class JForexTesterRunner {
    private JForexTesterRunner() {
    }

    public static void main(String[] args) throws Exception {
        JForexSessionConfig config = JForexSessionConfig.fromEnvironment(true);
        JForexMetrics metrics = JForexMetrics.start(config);
        Runtime.getRuntime().addShutdownHook(new Thread(metrics::close));

        ITesterClient client = TesterFactory.getDefaultInstance();
        client.connect(config.jnlpUri().toString(), config.username(), config.password());
        client.setDataInterval(
                ITesterClient.DataLoadingMethod.ALL_TICKS,
                config.startUtc().toEpochMilli(),
                config.endUtc().toEpochMilli()
        );
        client.startStrategy(new BehemothJForexStrategy(config, metrics));
    }
}
