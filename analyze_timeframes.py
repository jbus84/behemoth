import polars as pl
import os
from pathlib import Path
import datetime

# We will use the existing extract_patterns logic but vary forward_sec
from extract_patterns import extract_patterns
from model_patterns import train_and_discover # I'll modify model_patterns to return results

def run_sensitivity(idx_path, fx_root):
    horizons = [5, 10, 30, 60, 120]
    results = []
    
    for h in horizons:
        print(f"\n>>> TESTING HORIZON: {h} SECONDS")
        # Extract patterns for this horizon
        # Note: I'll modify extract_patterns to take output name
        extract_patterns(Path(idx_path), fx_root, forward_sec=h)
        
        # This creates lead_lag_patterns_NSXUSD.parquet (always same name)
        # Load and get basic stats as a proxy for the model
        df = pl.read_parquet("lead_lag_patterns_NSXUSD.parquet")
        
        # We are predicting: "Does the index move in the SAME direction as the FX burst?"
        # target=1: Follow (Trend)
        # target=0: Revert (Fade)
        
        follow_prob = df["target"].mean()
        revert_prob = 1 - follow_prob
        
        results.append({
            "Horizon (s)": h,
            "Revert Prob %": round(revert_prob * 100, 1),
            "Follow Prob %": round(follow_prob * 100, 1),
            "Samples": len(df)
        })
        
    print("\n--- Timeframe Sensitivity Analysis (NSXUSD) ---")
    print(pl.DataFrame(results))
    print("\nNote: We are predicting if the Index will REVERT or FOLLOW the 5s FX Burst direction.")

if __name__ == "__main__":
    idx_path = "/Users/danielfisher/Desktop/tick/NSXUSD/NSXUSD_202512_ticks.parquet"
    fx_root = "/Users/danielfisher/Desktop/tick"
    run_sensitivity(idx_path, fx_root)
