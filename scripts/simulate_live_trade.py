
import polars as pl
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from kalman_filter import KalmanFilterReg

def simulate_trade_execution():
    print("--- LIVE TRADE EXECUTION SIMULATION ---")
    print("Scenario: Gold (Y) vs Oil (X). Current Date: Dec 2025.")
    print("Z-Score hits +2.1 (Signal: SHORT Gold / BUY Oil).")
    
    # Mock Market Data
    price_gold = 2650.00
    price_oil = 75.00
    beta = 2.45 # From Kalman
    account_cash = 10000.00 # $10k Account
    leverage = 1.0 # No Leverage
    
    notional = account_cash * leverage
    
    # Sizing Logic
    # We want Dollar Neutrality on the Spread.
    # Spread = log(Y) - beta * log(X).
    # To trade this, we hold $N of Y and -$N of X? NO.
    # We are trading the beta-adjusted spread.
    # To neutralize market risk, we must weight by Beta.
    # Long Y ($1) vs Short X ($Beta).
    
    # Wait, let's check the Math again.
    # dSpread = dLogY - beta * dLogX
    # dSpread = (dY/Y) - beta * (dX/X)
    # We want PnL ~ dSpread.
    # If we hold $N position in Y, PnL_Y = $N * (dY/Y).
    # If we hold $M position in X, PnL_X = $M * (dX/X).
    # Total PnL = $N(dY/Y) + $M(dX/X).
    # We want Total PnL ~ (dY/Y) - beta(dX/X).
    # So we need $N = $PosSize.
    # And we need $M = -beta * $PosSize.
    
    # CORRECT: If Beta = 2.45, we need 2.45x more notional in Oil (X) than in Gold (Y).
    # Why? Because Oil is Less Volatile in percentage terms? Or More?
    # Beta = Vol_Y / Vol_X * Corr.
    # If Beta > 1, Y is more volatile (or correlated).
    
    # Let's verify with the "Dog Walker" analogy.
    # Y (Dog) moves 2.45% for every 1% X (Walker) moves.
    # Beta = 2.45.
    # If X moves +1%, Y moves +2.45%.
    # Spread (Residual) should be 0.
    # dSpread = 2.45% - 2.45(1%) = 0. Correct.
    # To hedge this in dollars:
    # If X moves +1%, we gain $M * 0.01.
    # If Y moves +2.45%, we lose $N * 0.0245.
    # We want Net PnL = 0.
    # $M * 0.01 = $N * 0.0245.
    # $M = 2.45 * $N.
    # So Notional_X = Beta * Notional_Y.
    
    # EXTREMELY IMPORTANT:
    # We hold Beta times more dollar value in X.
    
    pos_size_y = 1000.0 # Trade $1000 of Gold
    pos_size_x = pos_size_y * beta # Trade $2450 of Oil
    
    qty_gold = pos_size_y / price_gold
    qty_oil = pos_size_x / price_oil
    
    print("\n[Trade Signal]")
    print(f"Signal: **SHORT SPREAD** (Sell Y / Buy X)")
    print(f"Beta: {beta:.2f}")
    print("-" * 30)
    print(f"Leg 1 (Gold): SELL ${pos_size_y:.0f}  (Qty: {qty_gold:.4f} oz)")
    print(f"Leg 2 (Oil):  BUY  ${pos_size_x:.0f}  (Qty: {qty_oil:.2f} bbl)")
    print("-" * 30)
    print(f"Total Exposure: ${pos_size_y + pos_size_x:.2f}")
    print(f"Hedge Ratio: $1 Gold : ${beta:.2f} Oil")
    
    print("\n[Exit Signal]")
    print("Trigger: Z-Score crosses 0.00")
    print("Action: Close ALL positions immediately.")

if __name__ == "__main__":
    simulate_trade_execution()
