
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone

DATA_DIR = "data/global_4h"

# Tier 1 & 2 Pairs to Monitor
PAIRS = [
    ("FRXEUR", "BCOUSD", "CAC/Oil (Tier 1)"),
    ("XAUUSD", "BCOUSD", "Gold/Oil (Tier 1)"),
    ("USDCHF", "GRXEUR", "Swiss/DAX (Tier 1)"),
    ("FRXEUR", "EURGBP", "CAC/EURGBP (Tier 1)"),
]

def check_regime():
    print(f"--- MARKET REGIME INDICATOR (Threshold: Vol > 2.5) ---")
    print(f"Checking data in: {DATA_DIR}")
    print("| Pair | Current Volatility | Status | Action |")
    print("|---|---|---|---|")
    
    for y_sym, x_sym, label in PAIRS:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_4h.parquet")
        
        try:
            # We only need Y asset volatility for the "Heat" check
            # (Strategy requires Y to be moving to pay spread)
            if not os.path.exists(p_y):
                print(f"| {label} | N/A | MISSING | CHECK DATA |")
                continue
                
            df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"}).sort("timestamp")
            
            # Get last 200 bars
            if len(df_y) < 200:
                print(f"| {label} | N/A | NO DATA | WAIT |")
                continue
                
            y_log = np.log(df_y["Y"].tail(200).to_numpy())
            last_date = df_y["timestamp"].tail(1).item()
            
            # Calculate Volatility (Window 100)
            # Vol = Std(Diff(Log)) * 1000
            diffs = np.diff(y_log) # length 199
            
            # Use last 100 diffs
            vol_window = diffs[-100:] 
            vol = np.std(vol_window) * 1000
            
            status = "🟢 GREEN" if vol > 2.5 else "🔴 RED"
            action = "TRADE" if vol > 2.5 else "STAND ASIDE"
            
            print(f"| {label} | {vol:.2f} | {status} | {action} |")
            
        except Exception as e:
            print(f"Error {label}: {e}")

    print("-" * 40)
    print("Logic: Low Volatility (< 2.5) implies Alpha < Spread Cost.")

if __name__ == "__main__":
    check_regime()
