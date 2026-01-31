import polars as pl
import os

def analyze_trend_pnl(idx_name):
    # Load dataset
    input_file = f"full_year_dataset_{idx_name}.parquet"
    if not os.path.exists(input_file):
        print(f"Dataset {input_file} not found.")
        return
        
    df = pl.read_parquet(input_file)
    
    # Filter for Positive Regime (Trend Mode?)
    pos_regime = df.filter(pl.col("regime_corr_1h") > 0)
    
    # Strategy: Trend Follow (Target Trend = 1)
    # Trigger: FX Burst > 2bps
    # Action: Enter SAME direction as FX.
    
    # Calculate Outcomes
    trend_trades = pos_regime.filter(pl.col("fx_ret_5s").abs() >= 2.0)
    
    # Win = Market moved in SAME direction (target_trend == 1)
    wins = trend_trades.filter(pl.col("target_trend") == 1)
    losses = trend_trades.filter(pl.col("target_trend") == 0)
    
    win_rate = len(wins) / len(trend_trades) * 100
    
    # PnL Analysis (bps)
    # Win: Abs(FwdRet) - Spread
    # Loss: Abs(FwdRet) + Spread (assuming we stop out or hold to 30s)
    
    avg_win_bps = wins["fwd_ret_bps"].abs().mean()
    avg_loss_bps = losses["fwd_ret_bps"].abs().mean()
    avg_spread = trend_trades["spread"].mean()
    
    # Net EV
    ev = (win_rate/100 * (avg_win_bps - avg_spread)) - \
         ((1 - win_rate/100) * (avg_loss_bps + avg_spread))
         
    print(f"\n--- TREND FOLLOWING ANALYSIS (Positive Regime) ---")
    print(f"Dataset: {len(trend_trades)} events")
    print(f"Strategy: Follow FX Burst (Same Direction)")
    print(f"Win Rate: {win_rate:.2f}% (Low)")
    print(f"Avg Win:  {avg_win_bps:.3f} bps (High?)")
    print(f"Avg Loss: {avg_loss_bps:.3f} bps")
    print(f"Spread:   {avg_spread:.3f} bps")
    print(f"Net EV:   {ev:.3f} bps per trade")
    
    # Filter for Large Bursts (> 5bps) to see if Trend becomes cleaner
    large_bursts = trend_trades.filter(pl.col("fx_ret_5s").abs() > 5.0)
    if len(large_bursts) > 0:
        l_wins = large_bursts.filter(pl.col("target_trend") == 1)
        l_wr = len(l_wins) / len(large_bursts) * 100
        l_ev = (l_wr/100 * (l_wins["fwd_ret_bps"].abs().mean() - avg_spread)) - \
               ((1 - l_wr/100) * (large_bursts.filter(pl.col("target_trend") == 0)["fwd_ret_bps"].abs().mean() + avg_spread))
        print(f"\n--- LARGE BURST (>5bps) TREND ANALYSIS ---")
        print(f"Win Rate: {l_wr:.2f}%")
        print(f"Net EV:   {l_ev:.3f} bps")

if __name__ == "__main__":
    analyze_trend_pnl("NSXUSD")
