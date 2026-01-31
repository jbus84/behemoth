import polars as pl
import os

def optimize_positive_regime(idx_name):
    input_file = f"full_year_dataset_{idx_name}.parquet"
    if not os.path.exists(input_file):
        print(f"Dataset {input_file} not found.")
        return
        
    df = pl.read_parquet(input_file)
    
    # Filter for Positive Regime initially
    base_df = df.filter(pl.col("regime_corr_1h") > 0)
    
    # Calculate global constants for EV
    # We assume 'Reversion' trade (target_trend == 0)
    # Profit = Abs(FwdRet) - Spread
    # Loss = Abs(FwdRet) + Spread
    
    print(f"Base Dataset: {len(base_df)} events")
    
    # Grid Search
    burst_thresholds = [2.0, 3.0, 4.0, 5.0, 6.0]
    vol_thresholds = [0.5, 1.0, 1.5, 2.0] # Index Vol < X
    
    results = []
    
    for b_thresh in burst_thresholds:
        for v_thresh in vol_thresholds:
            # Apply Filters
            # 1. Burst Size > X
            # 2. Volatility < X (Quiet markets might be more mean-reverting?)
            subset = base_df.filter(
                (pl.col("fx_ret_5s").abs() >= b_thresh) &
                (pl.col("idx_vol_30s") < v_thresh)
            )
            
            if len(subset) < 100: continue # Ignore small samples
            
            # Calculate Win Rate (Reversion)
            reversion_trades = subset.filter(pl.col("target_trend") == 0)
            win_rate = len(reversion_trades) / len(subset) * 100
            
            # Calculate EV
            avg_win = reversion_trades["fwd_ret_bps"].abs().mean()
            if avg_win is None: avg_win = 0
            
            losing_trades = subset.filter(pl.col("target_trend") == 1)
            avg_loss = losing_trades["fwd_ret_bps"].abs().mean()
            if avg_loss is None: avg_loss = 0
            
            spread_cost = subset["spread"].mean()
            
            # EV = P(Win)*(Win-Spread) - P(Loss)*(Loss+Spread)
            # Simplified: Net PnL of all trades / count
            # Actually, let's just calc raw pnl per trade
            
            # Vectorized PnL Calculation
            # If Reversion (0): PnL = Abs(Ret) - Spread
            # If Trend (1): PnL = -Abs(Ret) - Spread
            
            pnl = subset.with_columns(
                pl.when(pl.col("target_trend") == 0)
                .then(pl.col("fwd_ret_bps").abs() - pl.col("spread"))
                .otherwise(-pl.col("fwd_ret_bps").abs() - pl.col("spread"))
                .alias("pnl")
            )
            
            net_ev = pnl["pnl"].mean()
            
            results.append({
                "Burst >": b_thresh,
                "Vol <": v_thresh,
                "Count": len(subset),
                "Win Rate": win_rate,
                "Net EV": net_ev
            })
            
    # Print Top 5 by EV
    results_df = pl.DataFrame(results).sort("Net EV", descending=True)
    print("\n--- OPTIMIZATION RESULTS (Positive Regime) ---")
    print(results_df.head(10))
    
    # Check if any hit > 70% WR
    best_wr = results_df.sort("Win Rate", descending=True).head(1)
    print("\nBest Win Rate Found:")
    print(best_wr)

if __name__ == "__main__":
    optimize_positive_regime("NSXUSD")
