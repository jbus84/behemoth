import polars as pl
import numpy as np

DATA_PATH = "/Users/danielfisher/repositories/behemoth/data/swing/NSXUSD_1h.parquet"

def run_audit():
    print(f"Loading {DATA_PATH}...")
    df = pl.read_parquet(DATA_PATH).sort("timestamp")
    
    # 1. Feature Engineering
    # Donchian 20-Day High on Hourly Data?
    # 20 Days = 20 * 24 = 480 hours.
    # Note: Traditional Donchian is 20 *Days*.
    # If we use 1H bars, lookback should be 480 bars.
    
    # Volatility Filter (ATR 20 Days)
    # ATR 20 Days = ATR(480 bars)
    
    print("Calculating Indicators (480h Lookback)...")
    df = df.with_columns([
        pl.col("high").rolling_max(window_size=480).alias("donchian_high"), 
        pl.col("low").rolling_min(window_size=480).alias("donchian_low"),
        pl.col("close").diff().abs().rolling_mean(window_size=480).alias("atr_long")
    ])
    
    # Calculate Regime
    atr_vals = df.select("atr_long").drop_nulls().to_series()
    high_vol_cutoff = atr_vals.quantile(0.66)
    low_vol_cutoff = atr_vals.quantile(0.33)
    
    print(f"High Vol Cutoff (ATR): {high_vol_cutoff:.2f}")

    # 2. Strategy Logic: "Time-Limited Breakout"
    # Entry: Close > Donchian High (Prev)
    # Exit: Market Close 8 hours later.
    # Implementation:
    # If Signal at T, we capture returns from T+1 to T+9 (8 bars).
    # Vectorized: Signal(T) * (Close(T+8) - Close(T))? 
    # Yes, accurate for "Fixed Holding Period".
    
    pdf = df.to_pandas()
    pdf["ref_high"] = pdf["donchian_high"].shift(1)
    pdf["ref_low"] = pdf["donchian_low"].shift(1)
    
    # Signal
    # Long Breakout
    pdf["long_entry"] = (pdf["close"] > pdf["ref_high"]).astype(int)
    # Short Breakout
    pdf["short_entry"] = (pdf["close"] < pdf["ref_low"]).astype(int)
    
    # Filter Regime (Avoid High Vol)
    # Note: We use ATR from T (Entry Time)
    pdf["is_safe"] = pdf["atr_long"] <= high_vol_cutoff
    
    # Filtered Entries
    pdf["long_signal"] = np.where(pdf["is_safe"] & (pdf["long_entry"] == 1), 1, 0)
    # pdf["short_signal"] = np.where(pdf["is_safe"] & (pdf["short_entry"] == 1), 1, 0) 
    # Focus on Longs for Nasdaq first? Or Both. Let's do Long Only first (Trend Bias).
    
    # 3. Calculate Returns (8-Hour Hold)
    # Return = (Close[T+8] - Close[T]) / Close[T] (or points)
    # We enter at Open of T+1? Or Close of T?
    # Standard backtest: Signal at Close T -> Enter Open T+1.
    # Exit at Close T+8 (8 hours later).
    
    # Forward Returns: (Open[T+1] to Close[T+8])
    # Can approximation: Close[T+8] - Open[T+1]
    
    # We need Open[T+1] and Close[T+8]
    pdf["entry_price"] = pdf["open"].shift(-1)
    pdf["exit_price"] = pdf["close"].shift(-8) # 8 hours later
    
    pdf["trade_pnl"] = pdf["exit_price"] - pdf["entry_price"]
    
    # Apply Signal
    pdf["pnl"] = pdf["long_signal"] * pdf["trade_pnl"]
    
    # Deduplicate Signals?
    # Donchian Breakout triggers continuously while above high.
    # We only want the *First* breakout (New High).
    # Logic: If long_entry[t] == 1 AND long_entry[t-1] == 0.
    
    pdf["new_breakout"] = np.where((pdf["long_signal"] == 1) & (pdf["long_signal"].shift(1) == 0), 1, 0)
    
    pdf["strategy_pnl"] = pdf["new_breakout"] * pdf["trade_pnl"]
    
    print("\n--- Results (8-Hour Max Hold) ---")
    total_pnl = pdf["strategy_pnl"].sum()
    trade_count = pdf["new_breakout"].sum()
    print(f"Total PnL: {total_pnl:.2f} Points")
    print(f"Trade Count: {trade_count}")
    print(f"Avg PnL per Trade: {total_pnl/trade_count:.2f}")
    
    # Win Rate
    wins = pdf[pdf["strategy_pnl"] > 0]["strategy_pnl"].count()
    print(f"Win Rate: {wins/trade_count:.2%}")
    
    # Yearly
    pdf["year"] = pdf["timestamp"].dt.year
    yearly = pdf.groupby("year")["strategy_pnl"].sum()
    print("\n--- Yearly PnL ---")
    print(yearly)

if __name__ == "__main__":
    run_audit()
