package com.behemoth.jforex;

import com.behemoth.jforex.core.ExecutionPort;
import com.behemoth.jforex.core.OrderHandle;
import com.behemoth.jforex.core.OrderResult;
import com.behemoth.jforex.core.OrderSubmissionRequest;
import com.behemoth.jforex.core.OrderRequest;
import com.dukascopy.api.IEngine;
import com.dukascopy.api.IOrder;
import com.dukascopy.api.Instrument;
import com.dukascopy.api.JFException;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;


final class JForexExecutionPort implements ExecutionPort {
    private final Supplier<IEngine> engineSupplier;
    private final Map<String, Instrument> instrumentsBySymbol;

    JForexExecutionPort(Supplier<IEngine> engineSupplier, Map<String, Instrument> instrumentsBySymbol) {
        this.engineSupplier = Objects.requireNonNull(engineSupplier, "engineSupplier");
        this.instrumentsBySymbol = Map.copyOf(Objects.requireNonNull(instrumentsBySymbol, "instrumentsBySymbol"));
    }

    @Override
    public OrderHandle submitStopOrder(OrderRequest request) {
        IEngine engine = requireEngine();
        Instrument instrument = requireInstrument(request.symbol());
        try {
            IOrder order = engine.submitOrder(
                    request.label(),
                    instrument,
                    "BUY".equals(request.side())
                            ? IEngine.OrderCommand.BUYSTOP
                            : IEngine.OrderCommand.SELLSTOP,
                    request.amountMillions(),
                    request.triggerPrice(),
                    request.stopLimitRangePips(),
                    0.0,
                    0.0,
                    request.goodTillEpochMs(),
                    request.comment()
            );
            return new OrderHandle(request.label(), order.getId());
        } catch (JFException exc) {
            throw new IllegalStateException(exc.getMessage(), exc);
        }
    }

    @Override
    public OrderResult submitMarketOrder(OrderSubmissionRequest request) {
        IEngine engine = requireEngine();
        Instrument instrument = requireInstrument(request.symbol());
        try {
            IEngine.OrderCommand command = request.side().equals("BUY")
                    ? IEngine.OrderCommand.BUY
                    : IEngine.OrderCommand.SELL;
            IOrder order = engine.submitOrder(
                    request.label(),
                    instrument,
                    command,
                    request.amountMillions()
            );
            return new OrderResult(order.getId(), order.getId(), request.reservationId());
        } catch (JFException exc) {
            throw new IllegalStateException(exc.getMessage(), exc);
        }
    }

    @Override
    public void cancelOrder(String symbol, String label) {
        IEngine engine = requireEngine();
        try {
            IOrder order = engine.getOrder(label);
            if (order != null) {
                order.close();
            }
        } catch (JFException exc) {
            throw new IllegalStateException(exc.getMessage(), exc);
        }
    }

    @Override
    public void closePosition(String symbol, String label) {
        IEngine engine = requireEngine();
        try {
            IOrder order = engine.getOrder(label);
            if (order != null) {
                order.close();
            }
        } catch (JFException exc) {
            throw new IllegalStateException(exc.getMessage(), exc);
        }
    }

    private IEngine requireEngine() {
        IEngine engine = engineSupplier.get();
        if (engine == null) {
            throw new IllegalStateException("JForex engine is not available");
        }
        return engine;
    }

    private Instrument requireInstrument(String symbol) {
        Instrument instrument = instrumentsBySymbol.get(symbol == null ? "" : symbol.trim().replace("/", "").toUpperCase());
        if (instrument == null) {
            throw new IllegalArgumentException("Unknown instrument: " + symbol);
        }
        return instrument;
    }
}
