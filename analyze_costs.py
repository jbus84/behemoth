import polars as pl
import os
from pathlib import Path
from extract_patterns import extract_patterns

def analyze_costs(idx_name, fx_root):
    # Load the patterns file (already generated)
    # If not exists, regenerate with default horizon just to get the timestamps
    pattern_file = f"lead_lag_patterns_{idx_name}.parquet"
    if not os.path.exists(pattern_file):
        print(f"Generating patterns for {idx_name}...")
        idx_path = Path(f"/Users/danielfisher/Desktop/tick/{idx_name}/{idx_name}_202512_ticks.parquet")
        extract_patterns(idx_path, fx_root, forward_sec=30)
    
    df = pl.read_parquet(pattern_file)
    
    # 1. Overall Average Spread of the dataset (for context)
    # We need to load the original index file for this, or just rely on what we have in patterns
    # The patterns df has 'spread' column from the join.
    # Note: 'spread' in extract_patterns is calculated as: ((ask-bid)/mid)*10000
    
    # Cost for specific patterns
    
    # A. General Reversion (Target=0)
    gen_reversion = df.filter(pl.col("target") == 0)
    gen_spread = gen_reversion["spread"].mean()
    
    # B. Momentum Exhaustion (> 4bps)
    mom_ex = df.filter(pl.col("fx_ret_5s").abs() > 4.0)
    mom_wins = mom_ex.filter(pl.col("target") == 0)
    mom_spread = mom_wins["spread"].mean()
    
    print(f"\n--- Cost Analysis: {idx_name} ---")
    print(f"Average Spread during General Reversion Wins: {gen_spread:.3f} bps")
    print(f"Average Spread during Momentum Exhaustion Wins: {mom_spread:.3f} bps")
    
    return {
        "Index": idx_name,
        "Gen_Spread": gen_spread,
        "Mom_Spread": mom_spread
    }

def main():
    fx_root = "/Users/danielfisher/Desktop/tick"
    indices = ["NSXUSD", "SPXUSD"]
    
    for idx in indices:
        analyze_costs(idx, fx_root)

if __name__ == "__main__":
    main()
