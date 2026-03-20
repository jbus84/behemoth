package com.behemoth.jforex.core;

public interface ExecutionPort {
    OrderHandle submitStopOrder(OrderRequest request);

    void enableNativeOco(String primaryLabel, String siblingLabel);

    void cancelOrder(String symbol, String label);

    /** Close an already-filled position at the strategy's initiative. */
    void closePosition(String symbol, String label);
}
