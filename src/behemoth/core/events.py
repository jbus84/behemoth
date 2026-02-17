from __future__ import annotations

from behemoth.core.exit_contract import ExitContract


def simulate_trade(
    entry_idx,
    direction,
    strategy_type,
    y,
    x,
    z_scores,
    active_asset,
    thresh=1.5,
    stop=3.5,
    cost_bps=0.0,
    exit_contract: ExitContract | None = None,
):
    """
    Simulate a single trade with Z-score exits only.
    Uses Z0 crossing + Z-based stop.
    """
    prices = y if active_asset == "Y" else x
    entry_price = prices[entry_idx]
    max_hold_bars = 500
    cross_zero_buffer_abs_z = 0.0
    stop_win_level_abs_z = float(stop)
    use_stop_win = True

    if exit_contract is not None:
        max_hold_bars = int(exit_contract.max_hold_bars)
        cross_zero_buffer_abs_z = float(exit_contract.cross_zero_buffer_abs_z)
        stop_win_level_abs_z = float(exit_contract.stop_win_level_abs_z)
        use_stop_win = bool(exit_contract.use_stop_win)

    for i in range(entry_idx + 1, min(entry_idx + max_hold_bars, len(z_scores))):
        z = z_scores[i]
        curr_price = prices[i]

        if strategy_type == "MOM":
            if direction == 1:  # Long
                if z < -cross_zero_buffer_abs_z:
                    pnl = (curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "LOSS_REV"
                if use_stop_win and z > stop_win_level_abs_z:
                    pnl = (curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "WIN_MOM"
            else:  # Short
                if z > cross_zero_buffer_abs_z:
                    pnl = -(curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "LOSS_REV"
                if use_stop_win and z < -stop_win_level_abs_z:
                    pnl = -(curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "WIN_MOM"

        else:  # REVERSION
            if direction == 1:  # Long
                if z > cross_zero_buffer_abs_z:
                    pnl = (curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "WIN_REV"
                if use_stop_win and z < -stop_win_level_abs_z:
                    pnl = (curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "LOSS_MOM"
            else:  # Short
                if z < -cross_zero_buffer_abs_z:
                    pnl = -(curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "WIN_REV"
                if use_stop_win and z > stop_win_level_abs_z:
                    pnl = -(curr_price - entry_price) * 10000 - cost_bps
                    return pnl, i - entry_idx, "LOSS_MOM"

    # Timeout
    timeout_idx = min(entry_idx + max_hold_bars - 1, len(prices) - 1)
    curr_price = prices[timeout_idx]
    if direction == 1:
        pnl = (curr_price - entry_price) * 10000 - cost_bps
    else:
        pnl = -(curr_price - entry_price) * 10000 - cost_bps
    return pnl, max_hold_bars, "TIMEOUT"
