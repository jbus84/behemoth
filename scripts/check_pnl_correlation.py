"""
Check PnL Correlation to explain Diversification Benefit.
"""
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.validation import _load_pipeline

def check_correlation():
    path = "data/events/events_h1_8yr_v3_mom.csv"
    print(f"Loading {path}...")
    df = _load_pipeline(path, 60)
    
    # Pivot to [Date, Pair] -> PnL
    # We need to aggregate by day first to get aligned timeseries
    df["date"] = pd.to_datetime(df["exit_ts"], unit="ns").dt.date
    
    daily_pnl = df.pivot_table(
        index="date", 
        columns="pair", 
        values="pnl_bps", 
        aggfunc="sum"
    ).fillna(0)
    
    # Compute Correlation Matrix
    corr = daily_pnl.corr()
    
    # Average Correlation (off-diagonal)
    mask = np.ones_like(corr, dtype=bool)
    mask[np.triu_indices_from(mask)] = False
    avg_corr = corr.values[mask].mean()
    
    print("\n=== PnL Correlation Analysis ===")
    print(f"Average Pairwise Correlation: {avg_corr:.4f}")
    
    print("\nTop Pair Correlations:")
    # Show a few pairs
    top_pairs = ["SPX/DAX", "GBP/JPY", "Gold/Oil", "AUD/CAD", "SPX/HK"]
    print(corr.loc[top_pairs, top_pairs].round(2))

if __name__ == "__main__":
    check_correlation()
