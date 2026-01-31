import polars as pl
import os

def analyze_frequency():
    idx_name = "NSXUSD"
    input_file = f"full_year_dataset_{idx_name}.parquet"
    
    if not os.path.exists(input_file):
        print(f"Dataset {input_file} not found.")
        return
        
    df = pl.read_parquet(input_file)
    total = len(df)
    
    # 1. Golden Zone (Neg Correlation < -0.2) -> 99% Reversion Win Rate
    golden_zone = df.filter(pl.col("regime_corr_1h") < -0.2)
    golden_count = len(golden_zone)
    golden_pct = (golden_count / total) * 100
    
    # 2. Trend Zone (Pos Correlation > 0.2) -> 85% Trend Win Rate
    trend_zone = df.filter(pl.col("regime_corr_1h") > 0.2)
    trend_count = len(trend_zone)
    trend_pct = (trend_count / total) * 100
    
    # 3. Noisy Zone (Flat Correlation between -0.2 and 0.2)
    noise_zone = df.filter((pl.col("regime_corr_1h") >= -0.2) & (pl.col("regime_corr_1h") <= 0.2))
    noise_count = len(noise_zone)
    noise_pct = (noise_count / total) * 100
    
    print(f"\n--- Regime Frequency (2025 Full Year: {total} Events) ---")
    print(f"1. Golden Zone (Fade Reg): {golden_count} events ({golden_pct:.1f}%)")
    print(f"2. Trend Zone (Follow Reg): {trend_count} events ({trend_pct:.1f}%)")
    print(f"3. Noisy Zone (Avoid):      {noise_count} events ({noise_pct:.1f}%)")
    
    # Average Duration of a Regime?
    # That would require robust timestamp analysis, simplified frequency is sufficient for now.
    
    # Calculate Trade Frequency per Day
    # Assuming 252 trading days roughly
    daily_golden = golden_count / 260
    print(f"\nExpected 'Golden Trades' per Day: ~{daily_golden:.1f}")

if __name__ == "__main__":
    analyze_frequency()
