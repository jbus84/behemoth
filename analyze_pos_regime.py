import polars as pl
import os
from pathlib import Path

def analyze_positive_regime(idx_name):
    # Load the Full Year dataset (already extracted)
    input_file = f"full_year_dataset_{idx_name}.parquet"
    if not os.path.exists(input_file):
        print(f"Dataset {input_file} not found.")
        return
        
    df = pl.read_parquet(input_file)
    
    # Filter for Positive Correlation Regime (> 0)
    pos_regime = df.filter(pl.col("regime_corr_1h") > 0)
    
    # Filter for "Reversion" Outcome (Target Trend = 0)
    reversion_trades = pos_regime.filter(pl.col("target_trend") == 0)
    
    # Win Rate of Reversion in Pos Regime
    win_rate = len(reversion_trades) / len(pos_regime) * 100
    
    # Average Win Size (bps)
    # Reversion means we Faded. So if FX went Up, Index went Down.
    # Our profit is the absolute move of the Index.
    avg_win_bps = reversion_trades["fwd_ret_bps"].abs().mean()
    
    # Average Loss Size (bps)
    trend_trades = pos_regime.filter(pl.col("target_trend") == 1)
    avg_loss_bps = trend_trades["fwd_ret_bps"].abs().mean()
    
    # Net Expectancy
    spread_cost = reversion_trades["spread"].mean()
    net_win = avg_win_bps - spread_cost
    ev = (win_rate/100 * net_win) - ((1 - win_rate/100) * (avg_loss_bps + spread_cost))
    
    print(f"\n--- POSITIVE REGIME ANALYSIS (The Scalp) ---")
    print(f"Dataset: {len(pos_regime)} events")
    print(f"Strategy: Fade (Reversion) in Positive Correlation")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Avg Win:  {avg_win_bps:.3f} bps")
    print(f"Avg Loss: {avg_loss_bps:.3f} bps")
    print(f"Avg Spread Cost: {spread_cost:.3f} bps")
    print(f"Net Win per Trade: {net_win:.3f} bps")
    print(f"Expected Value (EV): {ev:.3f} bps per trade")
    
    # Distribution
    print(f"\nWin Size Distribution:")
    print(reversion_trades["fwd_ret_bps"].abs().describe())

if __name__ == "__main__":
    analyze_positive_regime("NSXUSD")
