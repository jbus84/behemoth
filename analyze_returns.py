import polars as pl
import os
from pathlib import Path
from extract_patterns import extract_patterns

def analyze_horizon_returns(idx_name, horizon_s, fx_root):
    # 1. Generate Data
    idx_path = Path(f"/Users/danielfisher/Desktop/tick/{idx_name}/{idx_name}_202512_ticks.parquet")
    extract_patterns(idx_path, fx_root, forward_sec=horizon_s)
    
    # 2. Load Data
    df = pl.read_parquet(f"lead_lag_patterns_{idx_name}.parquet")
    
    # 3. Define Patterns
    # "Winning Trade" = We bet on Reversion (Fade) and we won.
    # So target == 0 (Index moved opposite to FX)
    
    # A. General Reversion (All Bursts > 2bps)
    general_wins = df.filter(pl.col("target") == 0)
    gen_avg_win = general_wins["fwd_ret_bps"].abs().mean()
    gen_win_rate = (len(general_wins) / len(df)) * 100
    
    # B. Momentum Exhaustion (> 4bps)
    # Burst > 4bps
    mom_ex = df.filter(pl.col("fx_ret_5s").abs() > 4.0)
    mom_wins = mom_ex.filter(pl.col("target") == 0)
    
    mom_avg_win = mom_wins["fwd_ret_bps"].abs().mean()
    if len(mom_ex) > 0:
        mom_win_rate = (len(mom_wins) / len(mom_ex)) * 100
    else:
        mom_win_rate = 0
        
    print(f"\n--- Returns Analysis: {idx_name} @ {horizon_s}s ---")
    print(f"[General Reversion] Win Rate: {gen_win_rate:.1f}% | Avg Win: {gen_avg_win:.3f} bps")
    print(f"[Momentum Exhaustion] Win Rate: {mom_win_rate:.1f}% | Avg Win: {mom_avg_win:.3f} bps")
    
    return {
        "Horizon": horizon_s,
        "Gen_WR": gen_win_rate,
        "Gen_Win": gen_avg_win,
        "Mom_WR": mom_win_rate,
        "Mom_Win": mom_avg_win
    }

def main():
    fx_root = "/Users/danielfisher/Desktop/tick"
    indices = ["NSXUSD", "SPXUSD"]
    horizons = [30, 120]
    
    for idx in indices:
        for h in horizons:
            analyze_horizon_returns(idx, h, fx_root)

if __name__ == "__main__":
    main()
