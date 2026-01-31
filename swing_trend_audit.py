import polars as pl
import numpy as np
import matplotlib.pyplot as plt

DATA_PATH = "/Users/danielfisher/repositories/behemoth/data/swing/NSXUSD_4h.parquet"

def run_audit():
    print(f"Loading {DATA_PATH}...")
    df = pl.read_parquet(DATA_PATH).sort("timestamp")
    
    # 1. Feature Engineering
    # Donchian 20
    # SMA 50, 200
    
    # Polars rolling functions
    # 4H data: 20 periods = 80 hours (approx 3.5 days). 
    # For Swing, usually Donchian 20 *Days* is standard.
    # On 4H, 20 days would be 20 * 6 = 120 periods.
    # Let's test multiple windows.
    
    windows = [20, 50, 100, 200, 500] 
    
    # Vectorized loop is hard in Polars for lazy eval, but eager is fine.
    
    print("Calculating Indicators...")
    df = df.with_columns([
        pl.col("close").rolling_mean(window_size=50).alias("sma_50"),
        pl.col("close").rolling_mean(window_size=200).alias("sma_200"),
        pl.col("high").rolling_max(window_size=120).alias("donchian_high_20d"), # 120 * 4h = 20 days
        pl.col("low").rolling_min(window_size=120).alias("donchian_low_20d"),
        pl.col("close").diff().alias("returns")
    ])
    
    # Drop nulls
    df = df.drop_nulls()
    
    # 2. Strategy Logic
    
    # Strategy A: Golden Cross (SMA 50 > SMA 200)
    # Signal: 1 if 50 > 200 else -1
    # Lag signal by 1 period to avoid lookahead (trade NEXT open/close)
    
    df = df.with_columns([
        (pl.col("sma_50") > pl.col("sma_200")).cast(pl.Int8).alias("signal_sma_raw")
    ])
    
    # Strategy B: Donchian Breakout
    # Long if Close > Donchian High (Prev). Short if Close < Donchian Low (Prev).
    # We need to construct a stateful signal (Trend Following).
    # Vectorized "Latch" logic:
    # Trigger Up: Close > High. Trigger Down: Close < Low.
    # We use forward fill.
    
    triggers = df.select([
        "timestamp", "close", "donchian_high_20d", "donchian_low_20d", "returns"
    ])
    
    # Conversion to pandas for easier stateful fill? Or Polars scan?
    # Pandas is safer for "ffill" logic of trade signals.
    pdf = triggers.to_pandas()
    
    # Shift Donchian to represent "Previous" logic (Standard breakout looks at PAST N days)
    # Donchian High of t-1 compared to Close t.
    pdf["ref_high"] = pdf["donchian_high_20d"].shift(1)
    pdf["ref_low"] = pdf["donchian_low_20d"].shift(1)
    
    conditions = [
        (pdf["close"] > pdf["ref_high"]), # Breakout Up
        (pdf["close"] < pdf["ref_low"])   # Breakout Down
    ]
    choices = [1, -1]
    
    pdf["signal_donchian"] = np.select(conditions, choices, default=np.nan)
    pdf["signal_donchian"] = pdf["signal_donchian"].ffill().fillna(0) # Hold position
    
    # SMA Signal (Pandas)
    pdf["sma_50"] = df["sma_50"].to_numpy()
    pdf["sma_200"] = df["sma_200"].to_numpy()
    pdf["signal_sma"] = np.where(pdf["sma_50"] > pdf["sma_200"], 1, -1)
    
    # 3. Regime Analysis (Volatility)
    df = df.with_columns([
        pl.col("high") - pl.col("low"), # Range
        pl.col("close").diff().abs().rolling_mean(window_size=20).alias("atr_20")
    ])
    
    # Define Volatility Regimes (Deciles) on the fly
    atr_values = df.select("atr_20").drop_nulls().to_series()
    # Approx Deciles
    low_vol = atr_values.quantile(0.33)
    high_vol = atr_values.quantile(0.66)
    
    print(f"ATRA Regimes: Low < {low_vol:.2f} | High > {high_vol:.2f}")
    
    # 4. Filtered Strategies
    pdf = df.select([
        "timestamp", "returns", "atr_20"
    ]).to_pandas()
    
    # Re-apply signals (imported/recalculated for simplicity)
    # We need the signals from previous step. 
    # Actually, simpler to just run the loop here or pass PDF.
    # Let's rebuild the PDF with everything.
    
    # Re-build PDF
    pdf = df.to_pandas()
    pdf["ref_high"] = pdf["donchian_high_20d"].shift(1)
    pdf["ref_low"] = pdf["donchian_low_20d"].shift(1)
    
    conditions = [
        (pdf["close"] > pdf["ref_high"]),
        (pdf["close"] < pdf["ref_low"])
    ]
    choices = [1, -1]
    
    pdf["signal_donchian"] = np.select(conditions, choices, default=np.nan)
    pdf["signal_donchian"] = pdf["signal_donchian"].ffill().fillna(0)
    
    # Filter: Low Vol Donchian vs High Vol Donchian
    pdf["vol_regime"] = np.where(pdf["atr_20"] > high_vol, "HIGH",
                                 np.where(pdf["atr_20"] < low_vol, "LOW", "MED"))
    
    # PnL Stream
    pdf["pnl_don"] = pdf["signal_donchian"].shift(1) * pdf["returns"]
    
    print("\n--- Volatility Regime Performance (Avg Daily PnL) ---")
    regime_stats = pdf.groupby("vol_regime")["pnl_don"].mean() * 252 # Annualized points approx? No 4H.
    # Just sum points
    regime_sum = pdf.groupby("vol_regime")["pnl_don"].sum()
    print(regime_sum)
    
    print("\n--- Donchian vs B&H (Cum) ---")
    print(f"Donchian Total: {pdf['pnl_don'].sum():.2f}")
    print(f"Buy & Hold: {pdf['returns'].sum():.2f}")
    
    # 5. Advanced Metrics (Duration & Drawdown)
    
    # A. Trade Duration
    # Identify trade starts (Signal diff != 0)
    pdf["trade_id"] = (pdf["signal_donchian"] != pdf["signal_donchian"].shift(1)).cumsum()
    # Filter for entries only (we only care about how long we hold a position)
    # Actually, groupby trade_id count * 4 hours.
    trades = pdf.groupby("trade_id")["timestamp"].count() * 4 # Hours
    avg_hours = trades.mean()
    print(f"\nAvg Trade Duration: {avg_hours:.1f} Hours ({avg_hours/24:.1f} Days)")
    
    # B. Drawdown Analysis
    def max_drawdown(series):
        cum = series.cumsum()
        peak = cum.cummax()
        dd = cum - peak
        return dd.min()

    dd_strat = max_drawdown(pdf["pnl_don"])
    dd_bh = max_drawdown(pdf["returns"])
    
    print(f"Max Drawdown (Strategy): {dd_strat:.2f}")
    print(f"Max Drawdown (B&H): {dd_bh:.2f}")
    
    # C. "Quiet Regime" Benchmark
    # B&H Return ONLY when Vol is LOW/MED (what are we comparing against?)
    mask_quiet = pdf["vol_regime"].isin(["LOW", "MED"])
    bh_quiet = pdf.loc[mask_quiet, "returns"].sum()
    strat_quiet = pdf.loc[mask_quiet, "pnl_don"].sum()
    
    print(f"\n--- Quiet Regime (Low/Med) Comparison ---")
    print(f"Strategy (Quiet): {strat_quiet:.2f}")
    print(f"B&H (Quiet Days): {bh_quiet:.2f}")
    
    # 2022 Specifics (The Crash)
    mask_2022 = pdf["timestamp"].dt.year == 2022
    strat_2022 = pdf.loc[mask_2022, "pnl_don"].sum()
    bh_2022 = pdf.loc[mask_2022, "returns"].sum()
    print(f"\n--- 2022 Bear Market Test ---")
    print(f"Strategy 2022: {strat_2022:.2f}")
    print(f"B&H 2022: {bh_2022:.2f}")

    # D. Sharpe Ratio
    # We need daily returns of the strategy.
    # Currently we have 'pnl_don' which is points.
    # To get Sharpe, we need % returns or log returns?
    # Sharpe is usually on % returns.
    # We don't have capital base here easily (Futures).
    # But we can estimate Sharpe using Points if we assume constant capital?
    # Or just mean(daily_points) / std(daily_points) * sqrt(252).
    # This is "Sharpe of PnL", which is valid for Futures.
    
    def calc_sharpe(series, freq=252):
        if series.std() == 0: return 0
        return series.mean() / series.std() * np.sqrt(freq)
        
    daily_pnl = pdf.set_index("timestamp").resample('1D')["pnl_don"].sum()
    sharpe_raw = calc_sharpe(daily_pnl)
    
    # Filtered Sharpe (Quiet Trend)
    # We only trade when vol is LOW/MED. 
    # Zero PnL on HIGH vol days.
    # We need to construct the daily series where High Vol days are 0.
    
    # Reconstruct daily PnL from the filtered series
    # In the PDF, "pnl_don" is raw.
    # We need "pnl_quiet".
    mask_high = pdf["vol_regime"] == "HIGH"
    pdf["pnl_quiet"] = np.where(mask_high, 0, pdf["pnl_don"])
    
    daily_pnl_quiet = pdf.set_index("timestamp").resample('1D')["pnl_quiet"].sum()
    sharpe_quiet = calc_sharpe(daily_pnl_quiet)
    
    # Buy & Hold Sharpe
    daily_bh = pdf.set_index("timestamp").resample('1D')["returns"].sum()
    sharpe_bh = calc_sharpe(daily_bh)
    
    print("\n--- Sharpe Ratios (Annualized) ---")
    print(f"Buy & Hold: {sharpe_bh:.2f}")
    print(f"Donchian (Raw): {sharpe_raw:.2f}")
    print(f"Donchian (Quiet Trend): {sharpe_quiet:.2f}")

if __name__ == "__main__":
    run_audit()
