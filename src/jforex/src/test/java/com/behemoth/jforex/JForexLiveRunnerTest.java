package com.behemoth.jforex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.dukascopy.api.IStrategy;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class JForexLiveRunnerTest {
    @Test
    void waitsForConnectionBeforeStartingStrategy() throws Exception {
        FakeClient client = new FakeClient(2);

        JForexLiveRunner.startWhenConnected(client, new NoOpStrategy(), 5, millis -> {
        });

        assertThat(client.connectCalls).isEqualTo(1);
        assertThat(client.connectedChecks).isEqualTo(3);
        assertThat(client.startStrategyCalls).isEqualTo(1);
    }

    @Test
    void failsWhenClientNeverConnects() {
        FakeClient client = new FakeClient(Integer.MAX_VALUE);

        assertThatThrownBy(() -> JForexLiveRunner.startWhenConnected(client, new NoOpStrategy(), 3, millis -> {
        }))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Failed to connect");
        assertThat(client.startStrategyCalls).isZero();
    }

    private static final class FakeClient implements JForexLiveRunner.LiveClient {
        private final int connectedAfterChecks;
        private final AtomicInteger checks = new AtomicInteger();
        private int connectCalls;
        private int startStrategyCalls;
        private int connectedChecks;

        private FakeClient(int connectedAfterChecks) {
            this.connectedAfterChecks = connectedAfterChecks;
        }

        @Override
        public void connect() {
            connectCalls++;
        }

        @Override
        public boolean isConnected() {
            connectedChecks++;
            return checks.getAndIncrement() >= connectedAfterChecks;
        }

        @Override
        public void startStrategy(IStrategy strategy) {
            startStrategyCalls++;
        }
    }

    private static final class NoOpStrategy implements IStrategy {
        @Override
        public void onStart(com.dukascopy.api.IContext context) {
        }

        @Override
        public void onTick(com.dukascopy.api.Instrument instrument, com.dukascopy.api.ITick tick) {
        }

        @Override
        public void onBar(
                com.dukascopy.api.Instrument instrument,
                com.dukascopy.api.Period period,
                com.dukascopy.api.IBar askBar,
                com.dukascopy.api.IBar bidBar
        ) {
        }

        @Override
        public void onMessage(com.dukascopy.api.IMessage message) {
        }

        @Override
        public void onAccount(com.dukascopy.api.IAccount account) {
        }

        @Override
        public void onStop() {
        }
    }
}
