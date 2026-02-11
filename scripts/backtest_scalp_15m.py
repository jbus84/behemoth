
import polars as pl
import numpy as np
import pandas as pd
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_15m"

# The 15m Scalping Candidates
PAIRS = [
    ("BCOUSD", "GRXEUR", "Oil/DAX"),
    ("BCOUSD", "SPXUSD", "Oil/SPX"),
    ("ETXEUR", "UKXGBP", "Euro/FTSE"),
    ("BCOUSD", "FRXEUR", "Oil/CAC"),
]

LEVERAGE = 30.0
INITIAL_CASH = 10000.0

def backtest_pair_advanced(y_name, x_name, label):
    print(f"\n--- Testing {label} ({y_name}/{x_name}) [REAL SPREADS + MARGIN] ---")

    # Load Data
    try:
        df_y = pl.read_parquet(os.path.join(DATA_DIR, f"{y_name}_15m.parquet"))
        df_x = pl.read_parquet(os.path.join(DATA_DIR, f"{x_name}_15m.parquet"))
    except Exception as e:
        print(f"Data not found: {e}")
        return

    # Align
    # We need Close (Bid) and Ask for both
    # Rename cols: close_X -> bid_X, ask_X -> ask_X

    # Ensure ask exists
    if f"ask_{y_name}" not in df_y.columns:
        print(f"Missing ask column for {y_name}")
        return

    df = df_y.rename({f"close_{y_name}": "bid_Y", f"ask_{y_name}": "ask_Y"}).join(
        df_x.rename({f"close_{x_name}": "bid_X", f"ask_{x_name}": "ask_X"}), on="timestamp", how="inner"
    ).sort("timestamp")

    # Strategy Params
    entry_z = 2.0
    exit_z = 0.0
    stop_z = 4.0

    # Kalman Setup
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)

    # We run Kalman on MID prices for signal stability
    y_mid = (df["bid_Y"].to_numpy() + df["ask_Y"].to_numpy()) / 2.0
    x_mid = (df["bid_X"].to_numpy() + df["ask_X"].to_numpy()) / 2.0

    y_logs = np.log(y_mid)
    x_logs = np.log(x_mid)

    # Execution Arrays (Vectorized lookup)
    bid_Y = df["bid_Y"].to_numpy()
    ask_Y = df["ask_Y"].to_numpy()
    bid_X = df["bid_X"].to_numpy()
    ask_X = df["ask_X"].to_numpy()

    timestamps = df["timestamp"].to_list()

    # Account State
    cash = INITIAL_CASH
    equity = INITIAL_CASH
    position_size_Y = 0.0 # Units
    position_size_X = 0.0 # Units
    entry_cost_basis = 0.0

    pnls = []

    # Kalman Warmup
    betas = []
    errors = []

    for i in range(len(y_logs)):
        b, _ = kf.update(x_logs[i], y_logs[i])
        betas.append(b)
        # Calculate error (Spread) on Mids
        # Error = Y_log - Beta * X_log (ignoring Alpha for Z-score calc, standard practice to mean center)
        # Wait, Kalman Reg gives instantaneous alpha. Let's use residual directly if possible, or standardized spread.
        # We will use the residual from the filter as the spread proxy.
        # residual = y - y_pred.
        # But we need Z-score.

        # Recalc spread explicitly using current Beta
        spread_val = y_logs[i] - b * x_logs[i]
        errors.append(spread_val)

    # Simulation Loop
    margin_calls = 0
    trades = 0

    window_size = 500

    for i in range(window_size, len(timestamps)):
        current_beta = betas[i-1] # Use lagged beta to avoid lookahead

        # Z-Score
        window = errors[i-window_size:i]
        mu = np.mean(window)
        std = np.std(window)

        current_spread = errors[i]

        if std < 1e-6:
            z = 0
        else:
            z = (current_spread - mu) / std

        # Margin Check
        # Update Equity
        # Mark to Market
        mtm_val = cash
        if position_size_Y != 0:
            # Value of positions
            # If Long Y: Value is bid_Y * size
            # If Short Y: Value is (Entry_Price - ask_Y) * size ... wait, simplified:
            # PnL = (Exit_Price - Entry_Price) * Size

            # Let's track floating equity
            val_Y, val_X = 0.0, 0.0

            # Y Leg
            if position_size_Y > 0: val_Y = (bid_Y[i] - entry_price_Y) * position_size_Y
            else: val_Y = (entry_price_Y - ask_Y[i]) * abs(position_size_Y)

            # X Leg
            if position_size_X > 0: val_X = (bid_X[i] - entry_price_X) * position_size_X
            else: val_X = (entry_price_X - ask_X[i]) * abs(position_size_X)

            equity = cash + val_Y + val_X

            # Margin Req
            # 30:1 Leverage = 3.33% Margin
            notional = (abs(position_size_Y) * bid_Y[i]) + (abs(position_size_X) * bid_X[i])
            used_margin = notional / LEVERAGE

            if equity < (used_margin * 0.5): # STOP OUT at 50% Margin Level
                margin_calls += 1
                # Force Close
                cash = equity # Realize loss
                position_size_Y = 0
                position_size_X = 0
                continue

        # Logic
        if position_size_Y == 0: # Flat
            if z > entry_z: # Short Spread (Sell Y, Buy X)
                # Sizing: Target $2000 Notional per leg (Conservative on $10k acc)
                target_notional = equity * 0.4 # 40% per leg -> 80% total exposure

                size_Y = target_notional / bid_Y[i] # Initial est
                size_X = size_Y * current_beta * (bid_Y[i]/bid_X[i]) # Match volatility? No, match beta value.
                # Beta is dY/dX. So Dollar_Y = Beta * Dollar_X roughly?
                # Actually: lnY = b*lnX -> dY/Y = b * dX/X
                # Dollar Volatility Y = Dollar Volatility X * b is wrong.
                # dY/Y (pct return) ~ b * dX/X (pct return).
                # To hedge Pct Return mismatch, we equalize Notional amounts?
                # If Beta=1, dY/Y = dX/X. $1000 in Y moves 1%, $1000 in X moves 1%.
                # So Equal Notionals hedge Beta=1.
                # If Beta=1.5, Y is 1.5x more volatile %. To hedge $1000 Y, we need $1500 X?
                # No. Spread = lnY - 1.5 lnX.
                # dSpread = dlnY - 1.5 dlnX = dY/Y - 1.5 dX/X.
                # To make dSpread PnL neutral to market?
                # PnL = N_y * dY/Y - N_x * dX/X.
                # We want PnL = C * dSpread.
                # N_y = Nominal. N_x = Nominal / Beta?
                # Let's stick to Dollar Neutral * Beta adjustment.
                # Standard: Short 1 unit Y, Long Beta units X?
                # Dollar amount: Y_amt = P_y, X_amt = Beta * P_x * (1? no).
                # Correct Hedge Ratio for Log Spread: $X = Beta * $Y.

                notional_Y = target_notional
                notional_X = target_notional * current_beta

                qty_Y = notional_Y / bid_Y[i]
                qty_X = notional_X / bid_X[i]

                # EXECUTE SHORT SPREAD
                # Sell Y (at Bid? No, Sell at Bid usually... wait. Sell usually hits Bid. Buy hits Ask.)
                entry_price_Y = bid_Y[i]
                entry_price_X = ask_X[i]
                position_size_Y = -qty_Y
                position_size_X = qty_X
                trades += 1

            elif z < -entry_z: # Long Spread (Buy Y, Sell X)
                target_notional = equity * 0.4
                notional_Y = target_notional
                notional_X = target_notional * current_beta

                qty_Y = notional_Y / ask_Y[i]
                qty_X = notional_X / bid_X[i]

                # EXECUTE LONG SPREAD
                entry_price_Y = ask_Y[i]
                entry_price_X = bid_Y[i]
                position_size_Y = qty_Y
                position_size_X = -qty_X
                trades += 1

        else: # In Position
            # Check Exit
            # Short Spread exits when Z < 0
            # Long Spread exits when Z > 0
            # Or Stop Loss Z > 4 / Z < -4

            do_exit = False
            if position_size_Y > 0: # Long Spread
                if z > exit_z or z < -stop_z: do_exit = True
            else: # Short Spread
                if z < -exit_z or z > stop_z: do_exit = True

            if do_exit:
                # Close
                # If Long Y: Sell at Bid
                # If Short X: Buy at Ask

                pnl_Y, pnl_X = 0.0, 0.0

                if position_size_Y > 0:
                    pnl_Y = (bid_Y[i] - entry_price_Y) * position_size_Y
                    pnl_X = (entry_price_X - ask_X[i]) * abs(position_size_X)
                else:
                    pnl_Y = (entry_price_Y - ask_Y[i]) * abs(position_size_Y)
                    pnl_X = (bid_X[i] - entry_price_X) * position_size_X

                total_pnl = pnl_Y + pnl_X
                cash += total_pnl
                position_size_Y = 0
                position_size_X = 0
                pnls.append(total_pnl)

    # Final Stats
    roi_pct = (cash - INITIAL_CASH) / INITIAL_CASH * 100.0
    dd = 0.0 # TODO: Calc Max Drawdown

    # Simple Sharpe (Trade based)
    if len(pnls) > 1:
        avg_trade = np.mean(pnls)
        std_trade = np.std(pnls)
        sharpe = (avg_trade / std_trade) * np.sqrt(trades) if std_trade > 1e-9 else 0
    else:
        sharpe = 0

    print(f"Final Equity: ${cash:.2f}")
    print(f"Total Trades: {trades}")
    print(f"ROI: {roi_pct:.2f}%")
    print(f"Sharpe (Trade): {sharpe:.2f}")
    print(f"Margin Calls: {margin_calls}")

if __name__ == "__main__":
    for y, x, lbl in PAIRS:
        backtest_pair_advanced(y, x, lbl)
