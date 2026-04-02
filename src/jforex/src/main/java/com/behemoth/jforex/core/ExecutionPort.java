package com.behemoth.jforex.core;

public interface ExecutionPort {
    OrderHandle submitStopOrder(OrderRequest request);

    /** Submit a single market order (BUY or SELL at current market price). */
    OrderHandle submitMarketOrder(MarketOrderRequest request);

    void cancelOrder(String symbol, String label);

    /** Close an already-filled position at the strategy's initiative. */
    void closePosition(String symbol, String label);
}
