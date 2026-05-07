package com.behemoth.jforex.core;

public interface ExecutionPort {
    OrderHandle submitStopOrder(OrderRequest request);

    /** Submit a lifecycle-aware market order (BUY or SELL at current market price). */
    default OrderResult submitMarketOrder(OrderSubmissionRequest request) {
        OrderHandle handle = submitMarketOrder(request.toMarketOrderRequest());
        return new OrderResult(handle.brokerOrderId(), handle.brokerOrderId(), request.reservationId());
    }

    /** Submit a single market order (BUY or SELL at current market price). */
    default OrderHandle submitMarketOrder(MarketOrderRequest request) {
        throw new UnsupportedOperationException("submitMarketOrder not implemented");
    }

    void cancelOrder(String symbol, String label);

    /** Close an already-filled position at the strategy's initiative. */
    void closePosition(String symbol, String label);
}
