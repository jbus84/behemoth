import polars as pl

# 1. Load New Accelerated Data
df = pl.read_csv("data/events/events_h1_8yr_v3_mom.csv")

# 2. Define Universes
fx_pairs = [
    "EUR/GBP", "AUD/NZD", "EUR/CHF", "EUR/JPY", "GBP/JPY", 
    "CHF/JPY", "EUR/AUD", "GBP/AUD", "AUD/CAD", "GBP/CAD", "NZD/CAD"
]

# 3. FX Stats (New)
fx_df = df.filter(pl.col("symbol").is_in(fx_pairs))
fx_trades = len(fx_df)
fx_avg = fx_df["pnl_bps"].mean()
fx_total = fx_df["pnl_bps"].sum()

print(f"--- FX UNIVERSE (Accelerated) ---")
print(f"Trades: {fx_trades}")
print(f"Avg PnL: {fx_avg:.2f} bps")
print(f"Total PnL: {fx_total:.2f} bps")

# 4. Compare with Known Baseline
# Baseline (from previous turn): 9465 trades, 8.4 bps avg, 79,877 total
base_trades = 9465
base_avg = 8.4
base_total = 79877

print(f"\n--- IMPROVEMENT (FX Only) ---")
print(f"Avg PnL: {base_avg} -> {fx_avg:.2f} (+{fx_avg - base_avg:.2f} bps)")
print(f"Total PnL: {base_total} -> {fx_total:.2f} ({((fx_total/base_total)-1)*100:.1f}%)")

# 5. Indices/Commodities (The "Bonus")
other_df = df.filter(~pl.col("symbol").is_in(fx_pairs))
other_avg = other_df["pnl_bps"].mean()
print(f"\n--- INDICES/COMMODITIES (Bonus) ---")
print(f"Trades: {len(other_df)}")
print(f"Avg PnL: {other_avg:.2f} bps")
