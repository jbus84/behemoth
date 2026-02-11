def simulate_trade(
    entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh=1.5, stop=3.5
):
    """
    Simulate a single trade with Z-score exits only.
    Uses Z0 crossing + Z-based stop.
    """
    prices = y if active_asset == "Y" else x
    entry_price = prices[entry_idx]

    for i in range(entry_idx + 1, min(entry_idx + 500, len(z_scores))):
        z = z_scores[i]
        curr_price = prices[i]

        if strategy_type == "MOM":
            if direction == 1:  # Long
                if z < 0:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "LOSS_REV"
                if z > stop:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "WIN_MOM"
            else:  # Short
                if z > 0:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "LOSS_REV"
                if z < -stop:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "WIN_MOM"

        else:  # REVERSION
            if direction == 1:  # Long
                if z > 0:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "WIN_REV"
                if z < -stop:
                    pnl = (curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "LOSS_MOM"
            else:  # Short
                if z < 0:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "WIN_REV"
                if z > stop:
                    pnl = -(curr_price - entry_price) * 10000
                    return pnl, i - entry_idx, "LOSS_MOM"

    # Timeout
    curr_price = prices[min(entry_idx + 499, len(prices) - 1)]
    if direction == 1:
        pnl = (curr_price - entry_price) * 10000
    else:
        pnl = -(curr_price - entry_price) * 10000
    return pnl, 500, "TIMEOUT"
