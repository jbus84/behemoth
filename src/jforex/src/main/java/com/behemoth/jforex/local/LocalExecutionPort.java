package com.behemoth.jforex.local;

import com.behemoth.jforex.adapter.OcoOrderPlan;
import com.behemoth.jforex.core.ExecutionPort;
import com.behemoth.jforex.core.OrderEvent;
import com.behemoth.jforex.core.OrderEventType;
import com.behemoth.jforex.core.OrderHandle;
import com.behemoth.jforex.core.OrderRequest;
import com.behemoth.jforex.core.RuntimeTick;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

public final class LocalExecutionPort implements ExecutionPort {
    private final Map<String, SimulatedOrder> ordersByLabel = new LinkedHashMap<>();
    private final Map<String, RuntimeTick> lastTickBySymbol = new LinkedHashMap<>();
    private final AtomicLong ids = new AtomicLong(1L);
    private Consumer<OrderEvent> eventListener = event -> {
    };

    public void setEventListener(Consumer<OrderEvent> eventListener) {
        this.eventListener = Objects.requireNonNull(eventListener, "eventListener");
    }

    @Override
    public OrderHandle submitStopOrder(OrderRequest request) {
        if (ordersByLabel.containsKey(request.label())) {
            throw new IllegalStateException("duplicate local order label: " + request.label());
        }
        String orderId = "LOCAL-" + ids.getAndIncrement();
        ordersByLabel.put(request.label(), new SimulatedOrder(request, orderId));
        emit(new OrderEvent(
                OrderEventType.SUBMIT_OK,
                request.symbol(),
                request.label(),
                orderId,
                0.0,
                null,
                0.0,
                null,
                null,
                "local_submit_ok",
                null
        ));
        return new OrderHandle(request.label(), orderId);
    }

    @Override
    public void enableNativeOco(String primaryLabel, String siblingLabel) {
        // Local surrogate always relies on manual sibling cancel.
    }

    @Override
    public void cancelOrder(String symbol, String label) {
        SimulatedOrder order = ordersByLabel.get(label);
        if (order == null || !order.isActive()) {
            return;
        }
        order.closed = true;
        RuntimeTick tick = lastTickBySymbol.getOrDefault(normalizeSymbol(symbol), null);
        Instant closeTs = tick == null ? order.request.submittedAtUtc() : tick.timestamp();
        emit(new OrderEvent(
                OrderEventType.CLOSE_OK,
                order.request.symbol(),
                order.request.label(),
                order.brokerOrderId,
                order.fillPrice,
                order.fillTimeUtc,
                0.0,
                closeTs,
                order.filled ? pnlPips(order, tick) : 0.0,
                order.filled ? "local_cancel_filled" : "local_cancel_pending",
                null
        ));
    }

    @Override
    public void closePosition(String symbol, String label) {
        cancelOrder(symbol, label);
    }

    public void onTick(RuntimeTick tick) {
        String symbol = normalizeSymbol(tick.symbol());
        lastTickBySymbol.put(symbol, tick);
        for (SimulatedOrder order : List.copyOf(ordersByLabel.values())) {
            if (!order.isPending() || !normalizeSymbol(order.request.symbol()).equals(symbol)) {
                continue;
            }
            if (tick.timestamp().toEpochMilli() > order.request.goodTillEpochMs()) {
                cancelOrder(symbol, order.request.label());
                continue;
            }
            if (!canFill(order, tick)) {
                continue;
            }
            order.filled = true;
            order.fillTimeUtc = tick.timestamp();
            order.fillPrice = order.request.side() == OcoOrderPlan.Side.BUY ? tick.ask() : tick.bid();
            emit(new OrderEvent(
                    OrderEventType.FILL_OK,
                    order.request.symbol(),
                    order.request.label(),
                    order.brokerOrderId,
                    order.fillPrice,
                    order.fillTimeUtc,
                    0.0,
                    null,
                    null,
                    "local_fill_ok",
                    null
            ));
        }
    }

    public void closeOpenOrdersAtEnd() {
        for (SimulatedOrder order : List.copyOf(ordersByLabel.values())) {
            if (!order.filled || order.closed) {
                continue;
            }
            RuntimeTick tick = lastTickBySymbol.get(normalizeSymbol(order.request.symbol()));
            if (tick == null) {
                continue;
            }
            order.closed = true;
            double closePrice = order.request.side() == OcoOrderPlan.Side.BUY ? tick.bid() : tick.ask();
            emit(new OrderEvent(
                    OrderEventType.CLOSE_OK,
                    order.request.symbol(),
                    order.request.label(),
                    order.brokerOrderId,
                    order.fillPrice,
                    order.fillTimeUtc,
                    closePrice,
                    tick.timestamp(),
                    pnlPips(order, tick),
                    "local_close_at_end",
                    null
            ));
        }
    }

    private boolean canFill(SimulatedOrder order, RuntimeTick tick) {
        double trigger = order.request.triggerPrice();
        double capPx = order.request.stopLimitRangePips() * order.request.pipSize();
        return switch (order.request.side()) {
            case BUY -> tick.ask() >= trigger && tick.ask() <= trigger + capPx;
            case SELL -> tick.bid() <= trigger && tick.bid() >= trigger - capPx;
        };
    }

    private double pnlPips(SimulatedOrder order, RuntimeTick tick) {
        if (!order.filled || tick == null) {
            return 0.0;
        }
        return switch (order.request.side()) {
            case BUY -> (tick.bid() - order.fillPrice) / order.request.pipSize();
            case SELL -> (order.fillPrice - tick.ask()) / order.request.pipSize();
        };
    }

    private void emit(OrderEvent event) {
        eventListener.accept(event);
    }

    private static String normalizeSymbol(String raw) {
        return raw == null ? "" : raw.trim().replace("/", "").toUpperCase();
    }

    private static final class SimulatedOrder {
        private final OrderRequest request;
        private final String brokerOrderId;
        private boolean filled;
        private boolean closed;
        private double fillPrice;
        private Instant fillTimeUtc;

        private SimulatedOrder(OrderRequest request, String brokerOrderId) {
            this.request = request;
            this.brokerOrderId = brokerOrderId;
        }

        private boolean isPending() {
            return !filled && !closed;
        }

        private boolean isActive() {
            return !closed;
        }
    }
}
