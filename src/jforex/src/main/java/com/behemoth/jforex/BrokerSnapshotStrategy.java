package com.behemoth.jforex;

import com.dukascopy.api.IAccount;
import com.dukascopy.api.IBar;
import com.dukascopy.api.IContext;
import com.dukascopy.api.IMessage;
import com.dukascopy.api.IOrder;
import com.dukascopy.api.IStrategy;
import com.dukascopy.api.ITick;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import com.dukascopy.api.Period;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;

final class BrokerSnapshotStrategy implements IStrategy {
    private final BrokerOrderSnapshotWriter writer;
    private final CountDownLatch completed;

    BrokerSnapshotStrategy(BrokerOrderSnapshotWriter writer, CountDownLatch completed) {
        this.writer = Objects.requireNonNull(writer, "writer");
        this.completed = Objects.requireNonNull(completed, "completed");
    }

    @Override
    public void onStart(IContext context) throws JFException {
        try {
            List<BrokerOrderSnapshotWriter.BrokerSnapshotOrder> snapshotOrders = new ArrayList<>();
            for (IOrder order : context.getEngine().getOrders()) {
                snapshotOrders.add(
                        new BrokerOrderSnapshotWriter.BrokerSnapshotOrder(
                                String.valueOf(order.getId()),
                                order.getLabel(),
                                normalizeSymbol(order.getInstrument().name()),
                                order.getState().name(),
                                order.getOrderCommand().name()
                        )
                );
            }
            writer.write(Instant.now(), snapshotOrders);
            context.stop();
        } catch (Exception exc) {
            throw new JFException(exc.getMessage());
        }
    }

    @Override
    public void onTick(Instrument instrument, ITick tick) {
    }

    @Override
    public void onBar(Instrument instrument, Period period, IBar askBar, IBar bidBar) {
    }

    @Override
    public void onMessage(IMessage message) {
    }

    @Override
    public void onAccount(IAccount account) {
    }

    @Override
    public void onStop() {
        completed.countDown();
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.replace("/", "").trim().toUpperCase();
    }
}
