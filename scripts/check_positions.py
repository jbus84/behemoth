
import requests
import pandas as pd
import sys

API_URL = "http://127.0.0.1:8000"

def check_positions():
    try:
        resp = requests.get(f"{API_URL}/positions")
        resp.raise_for_status()
        positions = resp.json()
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return

    if not positions:
        print("No positions found in DB.")
        return

    df = pd.DataFrame(positions)
    print(f"Total Positions: {len(df)}")
    
    if "strategy_id" not in df.columns:
        print("strategy_id column missing")
        return

    # Group by strategy
    strategies = df["strategy_id"].unique()
    print(f"Strategies: {strategies}")

    for strat in strategies:
        print(f"\n--- Strategy: {strat} ---")
        sdf = df[df["strategy_id"] == strat].copy()
        
        # Check PnL
        if "pnl_bps" in sdf.columns:
            # Convert to numeric, coerce errors
            sdf["pnl_bps"] = pd.to_numeric(sdf["pnl_bps"], errors="coerce")
            
            completed = sdf[sdf["status"] == "CLOSED"]
            print(f"Closed Trades: {len(completed)}")
            if len(completed) > 0:
                print(f"Mean PnL: {completed['pnl_bps'].mean():.2f} bps")
                print(f"Total PnL: {completed['pnl_bps'].sum():.2f} bps")
                print(f"Win Rate: {(completed['pnl_bps'] > 0).mean():.2%}")
                
                # Show last 5 trades
                print("\nLast 5 Trades:")
                print(completed[["pair", "side", "entry_price", "exit_price", "pnl_bps", "exit_ts"]].tail(5).to_string())
        else:
            print("No pnl_bps column")

if __name__ == "__main__":
    check_positions()
