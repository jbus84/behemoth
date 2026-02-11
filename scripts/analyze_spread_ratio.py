
import polars as pl
import numpy as np
import os

DATA_DIR_15M = "data/global_15m"
DATA_DIR_4H = "data/global_4h"

PAIR = "EURUSD"

def analyze_ratios():
    print(f"--- SPREAD RATIO ANALYSIS ({PAIR}) ---")

    # Cost in BPS
    # 1 pip on EURUSD (1.0500) = 0.0001 / 1.0500 = 0.95 bps
    # Spread = 1.0 pips = ~1.0 bps
    # Commission = $7/lot = ~0.7 bps
    # Total Cost = ~1.7 bps per leg.
    # Pair Trading = 2 Legs = ~3.5 bps.
    COST_BPS = 3.5

    # 15M Data
    p_15m = os.path.join(DATA_DIR_15M, f"{PAIR}_15m.parquet")
    df_15m = pl.read_parquet(p_15m)

    # Calculate Moves (Close-to-Close)
    close_15 = df_15m[f"close_{PAIR}"].to_numpy()
    # Drop first NaNs from diff
    moves_15 = np.abs(np.diff(np.log(close_15))) * 10000
    avg_move_15 = np.mean(moves_15)

    # 4H Data
    p_4h = os.path.join(DATA_DIR_4H, f"{PAIR}_4h.parquet")
    df_4h = pl.read_parquet(p_4h)

    close_4h = df_4h[f"close_{PAIR}"].to_numpy()
    moves_4h = np.abs(np.diff(np.log(close_4h))) * 10000
    avg_move_4h = np.mean(moves_4h)

    print(f"Cost Basis (2 Legs): {COST_BPS} bps")
    print("-" * 30)
    print(f"[M15] Avg Bar Move:  {avg_move_15:.2f} bps")
    print(f"[M15] Cost Impact:   {(COST_BPS / avg_move_15)*100:.1f}% of the move")
    print("-" * 30)
    print(f"[H4]  Avg Bar Move:  {avg_move_4h:.2f} bps")
    print(f"[H4]  Cost Impact:   {(COST_BPS / avg_move_4h)*100:.1f}% of the move")
    print("-" * 30)

    if (COST_BPS / avg_move_15) > 0.20:
        print("Verdict: M15 is UNTRADEABLE (Cost > 20% of Volatility).")
    else:
        print("Verdict: M15 is VIABLE.")

if __name__ == "__main__":
    analyze_ratios()
