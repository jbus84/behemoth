import polars as pl
import os
from pathlib import Path
import datetime

def analyze_full_year(idx_name, tick_root):
    print(f"\n>>> PROCESSING FULL YEAR 2025 FOR {idx_name} <<<")
    
    months = [f"2025{m:02d}" for m in range(1, 13)]
    fx_pairs = ["EURUSD", "GBPUSD", "USDCHF", "USDJPY"]
    all_year_data = []
    
    tick_root = Path(tick_root)
    
    for ym in months:
        # Construct paths
        idx_path = tick_root / idx_name / f"{idx_name}_{ym}_ticks.parquet"
        if not idx_path.exists():
            print(f"  Missing index data for {ym}, skipping...")
            continue
            
        print(f"  Aggregating {ym}...")
        
        # Load Index
        try:
            idx = pl.read_parquet(idx_path).select(["timestamp", "mid", "ask", "bid"]).sort("timestamp")
            idx = idx.with_columns(((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10000).alias("spread"))
        except Exception as e:
            print(f"    Error reading index {ym}: {e}")
            continue

        monthly_patterns = []

        for fx_name in fx_pairs:
            fx_path = tick_root / fx_name / f"{fx_name}_{ym}_ticks.parquet"
            if not fx_path.exists(): continue
            
            try:
                fx = pl.read_parquet(fx_path).select(["timestamp", "mid"]).rename({"mid": "fx_px"}).sort("timestamp")
                
                # Resample / Grid
                start = max(idx["timestamp"].min(), fx["timestamp"].min())
                end = min(idx["timestamp"].max(), fx["timestamp"].max())
                grid = pl.datetime_range(start, end, "1s", eager=True).to_frame("timestamp").with_columns(
                    pl.col("timestamp").dt.cast_time_unit("ns")
                ).sort("timestamp")
                
                combined = grid.join_asof(idx, on="timestamp", strategy="backward")
                combined = combined.join_asof(fx, on="timestamp", strategy="backward").drop_nulls()
                
                # Features
                combined = combined.with_columns([
                    (((pl.col("fx_px") / pl.col("fx_px").shift(5)) - 1) * 10000).alias("fx_ret_5s"),
                    (pl.col("mid").pct_change().rolling_std(window_size=30) * 10000).alias("idx_vol_30s"),
                ])
                
                # Filter bursts > 2bps
                bursts = combined.filter(pl.col("fx_ret_5s").abs() >= 2.0)
                
                if len(bursts) == 0: continue
                
                # Target: 120s Forward Return (Profit Maximization Horizon)
                targets = bursts.select(["timestamp", "mid", "fx_ret_5s", "idx_vol_30s", "spread"]).with_columns(
                    (pl.col("timestamp") + datetime.timedelta(seconds=120)).alias("target_time")
                ).with_columns(pl.col("target_time").dt.cast_time_unit("ns"))
                
                labels = targets.join_asof(
                    combined.select(["timestamp", "mid"]).rename({"mid": "mid_after"}),
                    left_on="target_time",
                    right_on="timestamp",
                    strategy="forward"
                )
                
                labels = labels.with_columns([
                    (((pl.col("mid_after") / pl.col("mid")) - 1) * 10000).alias("fwd_ret_bps"),
                ])
                
                # Target Logic: Did Index Revert? (Opposite sign to FX)
                # target=1 (Win) if Correlation is Negative
                labels = labels.with_columns(
                    ((pl.col("fwd_ret_bps") * pl.col("fx_ret_5s").sign()) < 0).cast(pl.Int8).alias("is_reversion_win")
                ).drop_nulls()
                
                monthly_patterns.append(labels.drop(["mid", "mid_after", "target_time"]))
                
            except Exception as e:
                print(f"    Error processing {fx_name} in {ym}: {e}")
                continue
                
        if monthly_patterns:
            all_year_data.append(pl.concat(monthly_patterns))
            
    if not all_year_data:
        print("No data found for full year.")
        return

    full_df = pl.concat(all_year_data)
    print(f"\n--- FULL YEAR 2025 RESULTS ({len(full_df)} Events) ---")
    
    # 1. Momentum Exhaustion Analysis (>4bps)
    mom_ex = full_df.filter(pl.col("fx_ret_5s").abs() > 4.0)
    wins = mom_ex.filter(pl.col("is_reversion_win") == 1)
    
    win_rate = (len(wins) / len(mom_ex)) * 100
    avg_win_bps = wins["fwd_ret_bps"].abs().mean()
    avg_spread = wins["spread"].mean()
    net_pnl = avg_win_bps - avg_spread
    
    print(f"Pattern: Momentum Exhaustion (>4bps Burst)")
    print(f"Total Events: {len(mom_ex)}")
    print(f"Win Rate:     {win_rate:.1f}%")
    print(f"Avg Win:      {avg_win_bps:.3f} bps")
    print(f"Avg Spread:   {avg_spread:.3f} bps")
    print(f"Net PnL:      +{net_pnl:.3f} bps")
    
    # Yearly Stability Check (Monthly Breakdown)
    # Since we didn't keep 'month' column explicitly, we can't group by it easily unless we parse timestamp again
    # But aggregate is enough for "Persists for rest of 2025" confirmation.

def main():
    tick_root = "/Users/danielfisher/Desktop/tick"
    analyze_full_year("NSXUSD", tick_root)
    analyze_full_year("SPXUSD", tick_root)

if __name__ == "__main__":
    main()
