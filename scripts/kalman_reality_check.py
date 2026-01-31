
import polars as pl
import numpy as np
import pandas as pd
import os
from kalman_filter import KalmanFilterReg

DATA_DIR = "/Users/danielfisher/repositories/behemoth/data/pairs"

def calc_daily_sharpe(df_pnl):
    # Aggregates PnL by Day and calculates Sharpe
    daily = df_pnl.set_index("timestamp").resample("1D")["pnl"].sum()
    if daily.std() == 0: return 0.0
    return daily.mean() / daily.std() * np.sqrt(252)

def run_stress_test(pair_name, parquet_file, col_y, col_x, cost_bps=0.0003):
    path = f"{DATA_DIR}/{parquet_file}"
    if not os.path.exists(path):
        print(f"Skipping {pair_name}: Data not found.")
        return

    print(f"\n=== Stress Test: {pair_name} ===")
    print(f"Loading {path}...")
    df = pl.read_parquet(path).sort("timestamp")
    
    # 1. State Update (Kalman)
    # y = beta * x
    y_raw = np.log(df[col_y].to_numpy())
    x_raw = np.log(df[col_x].to_numpy())
    timestamps = df["timestamp"].to_list()
    
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    
    spreads = []
    betas = []
    
    # Walk-Forward Filter
    for i in range(len(y_raw)):
        beta, spread = kf.update(x_raw[i], y_raw[i])
        betas.append(beta)
        spreads.append(spread)
        
    # convert to pandas for rolling ops
    s_series = pd.Series(spreads)
    
    # Robust Z-Score (Rolling Window only)
    # We use a 30-period rolling window to normalize.
    # This avoids "Full Sample" bias.
    rolling_mean = s_series.rolling(30).mean()
    rolling_std = s_series.rolling(30).std()
    z_score = (s_series - rolling_mean) / rolling_std
    
    # 2. Backtest Loop (With Costs)
    signals = np.zeros(len(z_score))
    position = 0
    pnl = []
    costs = []
    
    # Rules
    ENTRY_THRESH = 2.0
    EXIT_THRESH = 0.0
    
    for i in range(1, len(z_score)):
        # Signal Generation (Using t-1 info)
        z = z_score.iloc[i-1]
        
        # Determine Target Position
        target_pos = position
        if position == 0:
            if z > ENTRY_THRESH: target_pos = -1 # Short Spread
            elif z < -ENTRY_THRESH: target_pos = 1 # Long Spread
        elif position == 1:
            if z > EXIT_THRESH: target_pos = 0 # Exit Long
        elif position == -1:
            if z < -EXIT_THRESH: target_pos = 0 # Exit Short
            
        # Cost Calculation
        # Change in position * cost
        # We assume cost_bps applies to the gross notional.
        # Check: 1 unit of spread ~ 1 unit of asset?
        # Log spread = log(y) - b*log(x).
        # A change of 0.0003 in log price is 3bps.
        # So we can subtract cost_bps directly from log-pnl.
        
        vol_traded = abs(target_pos - position)
        tx_cost = vol_traded * cost_bps
        costs.append(tx_cost)
        
        # PnL Calculation
        # (Spread[t] - Spread[t-1]) * Position
        step_pnl = (spreads[i] - spreads[i-1]) * position
        
        # Net PnL
        net_step_pnl = step_pnl - tx_cost
        pnl.append(net_step_pnl)
        
        # Update State
        position = target_pos
        signals[i] = position
        
    # 3. Aggregation & Metrics
    df_res = pd.DataFrame({
        "timestamp": timestamps[1:],
        "pnl": pnl,
        "cost": costs,
        "position": signals[1:]
    })
    
    total_pnl = df_res["pnl"].sum()
    total_cost = df_res["cost"].sum()
    
    # Daily Sharpe
    daily_sharpe = calc_daily_sharpe(df_res)
    
    print(f"Total Net PnL (Log Units): {total_pnl:.4f}")
    print(f"Total Costs Paid: {total_cost:.4f} ({total_cost/abs(total_pnl+total_cost)*100:.1f}% of Gross)")
    print(f"Daily Sharpe (Annualized): {daily_sharpe:.2f}")
    
    # Yearly Breakdown
    print("\n--- Yearly Performance ---")
    df_res["year"] = pd.to_datetime(df_res["timestamp"]).dt.year
    years = df_res.groupby("year")
    
    for year, group in years:
        y_pnl = group["pnl"].sum()
        y_sharpe = calc_daily_sharpe(group)
        print(f"{year}: PnL {y_pnl:.4f} | Sharpe {y_sharpe:.2f}")

    # Duration
    n_trades = df_res[df_res["cost"] > 0].shape[0] / 2 # Entry + Exit
    if n_trades > 0:
        avg_pnl_trade = total_pnl / n_trades
        print(f"\nAvg PnL per Trade: {avg_pnl_trade*10000:.1f} bps")
        print(f"Total Trades: {int(n_trades)}")
    else:
        print("\nNo Trades.")

if __name__ == "__main__":
    # Nasdaq vs SPX
    run_stress_test("Nasdaq / SPX", "pairs_indices_4h.parquet", "close_NSXUSD", "close_SPXUSD", cost_bps=0.0003)
    
    # EUR / GBP
    run_stress_test("EUR / GBP", "pairs_fx_4h.parquet", "close_EURUSD", "close_GBPUSD", cost_bps=0.0002)
    
    # DAX / FTSE
    run_stress_test("DAX / FTSE", "pairs_dax_ftse_4h.parquet", "close_GRXEUR", "close_UKXGBP", cost_bps=0.0003)

    # AUD / NZD (Cross) - Higher spread assumption (3bps)
    run_stress_test("AUD / NZD", "pairs_aud_nzd_4h.parquet", "close_AUDUSD", "close_NZDUSD", cost_bps=0.0003)

    # EUR / CHF (Safe Haven)
    run_stress_test("EUR / CHF", "pairs_eur_chf_4h.parquet", "close_EURUSD", "close_USDCHF", cost_bps=0.0002)

    # Metals (Gold/Silver) - 3bps
    run_stress_test("Gold / Silver", "pairs_metals_4h.parquet", "close_XAUUSD", "close_XAGUSD", cost_bps=0.0003)

    # Yen (USD/EUR) - 2bps
    run_stress_test("USDJPY / EURJPY", "pairs_yen_4h.parquet", "close_USDJPY", "close_EURJPY", cost_bps=0.0002)

    # Oil / CAD - 3bps
    run_stress_test("Brent / CAD", "pairs_oil_cad_4h.parquet", "close_BCOUSD", "close_USDCAD", cost_bps=0.0003)
