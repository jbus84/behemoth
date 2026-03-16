package com.behemoth.jforex;

import com.behemoth.jforex.config.JForexSessionConfig;
import com.dukascopy.api.system.ClientFactory;
import com.dukascopy.api.system.IClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class JForexConnectionTest {
    private static final Logger log = LoggerFactory.getLogger(JForexConnectionTest.class);

    public static void main(String[] args) {
        // Start a daemon thread that will forcefully terminate the JVM after 15 seconds
        Thread timeoutThread = new Thread(() -> {
            try {
                Thread.sleep(15000);
                log.error("❌ Connection test timed out after 15 seconds!");
                System.exit(1);
            } catch (InterruptedException ignored) {
            }
        });
        timeoutThread.setDaemon(true);
        timeoutThread.start();

        try {
            log.info("Starting JForex connection test...");
            JForexSessionConfig config = JForexSessionConfig.fromEnvironment(false);
            IClient client = ClientFactory.getDefaultInstance();

            log.info("Attempting to connect to {}", config.jnlpUri());

            client.connect(config.jnlpUri().toString(), config.username(), config.password());

            int maxWaitSeconds = 15;
            for (int i = 0; i < maxWaitSeconds; i++) {
                if (client.isConnected()) {
                    log.info("✅ Successfully connected to JForex API!");
                    client.disconnect();
                    System.exit(0);
                }
                Thread.sleep(1000);
            }

            log.error("❌ Failed to connect within {} seconds", maxWaitSeconds);
            System.exit(1);

        } catch (Exception e) {
            log.error("❌ Exception during connection test", e);
            System.exit(1);
        }
    }
}
