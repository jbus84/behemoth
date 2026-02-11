
import polars as pl
import numpy as np
import os
from itertools import combinations
from kalman_filter import KalmanFilterReg
from datetime import datetime, timezone

DATA_DIR = "data/global_1h"
COST_BPS = 2.0

def scan_full_universe():
    print("--- 2025 FULL FX UNIVERSE SCAN (H1) ---")

    # 1. Identify  Files
    files = [f for f in os.listdir(DATA_DIR) if f.endswith("_1h.parquet")]
    fx_files = []
    # Identify currencies and indices
    valid_assets = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD", "FRX", "GRX", "SPX", "NSX", "UKX", "BCO", "XAU", "XAG"]

    for f in files:
        sym = f.split("_")[0]
        # Basic check: first 3 chars or last 3 chars must be currency/asset
        for v in valid_assets:
            if v in sym:
                fx_files.append(sym)
                break
    fx_files = list(set(fx_files)) # dedupe

    print(f"Identified {len(fx_files)} Instruments")

    # 2. Generate Pairs
    pairs = list(combinations(fx_files, 2))
    print(f"Testing {len(pairs)} permutations...")

    results = []

    # 3. Scan
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2025, 12, 31, tzinfo=timezone.utc)

    count = 0
    for y_sym, x_sym in pairs:
        res = test_pair_gross(y_sym, x_sym, start_dt, end_dt)
        if res:
            results.append(res)

        count += 1
        if count % 20 == 0:
            print(f"Processed {count}/{len(pairs)}...")

    # 4. Report Top 20 by NET PnL
    results.sort(key=lambda x: x['net'], reverse=True)

    print("\n--- TOP 20 PAIRS (2025: Gross vs Spread vs Net) ---")
    print("| Rank | Pair | Gross PnL | Spread Cost | **Net PnL** | Trades |")
    print("|---|---|---|---|---|---|")

    for i, res in enumerate(results[:20]):
        rank = i + 1
        label = f"{res['y']}/{res['x']}"
        print(f"| {rank} | {label} | {res['gross']:.2f} | -{res['cost']:.2f} | **{res['net']:.2f}** | {res['trades']} |")

    print("\n--- NOTABLE COMMODITY/INDEX PAIRS ---")
    special = [r for r in results if "XAU" in r['y'] or "XAU" in r['x'] or "FRX" in r['y'] or "FRX" in r['x'] or "BCO" in r['y']]
    special.sort(key=lambda x: x['net'], reverse=True)
    for i, res in enumerate(special[:10]):
        label = f"{res['y']}/{res['x']}"
        print(f"| Spec | {label} | {res['gross']:.2f} | -{res['cost']:.2f} | **{res['net']:.2f}** | {res['trades']} |")

def test_pair_gross(y_sym, x_sym, start_dt, end_dt):
    try:
        p_y = os.path.join(DATA_DIR, f"{y_sym}_1h.parquet")
        p_x = os.path.join(DATA_DIR, f"{x_sym}_1h.parquet")

        df_y = pl.read_parquet(p_y)
        df_x = pl.read_parquet(p_x)

        # Check for spread columns
        has_spread_y = f"spread_{y_sym}" in df_y.columns
        has_spread_x = f"spread_{x_sym}" in df_x.columns

        df = df_y.rename({f"close_{y_sym}": "Y", f"spread_{y_sym}": "SY"} if has_spread_y else {f"close_{y_sym}": "Y"}).join(
            df_x.rename({f"close_{x_sym}": "X", f"spread_{x_sym}": "SX"} if has_spread_x else {f"close_{x_sym}": "X"}),
            on="timestamp", how="inner"
        ).filter(
            (pl.col("timestamp") >= start_dt) & (pl.col("timestamp") <= end_dt)
        ).sort("timestamp")

        if len(df) < 200: return None

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())

        # Calculate Spread Costs (in BPS)
        # Cost = (Spread / Price) * 10000
        # If missing, assume 2.0 bps default
        if has_spread_y: cost_y = (df["SY"] / df["Y"]).mean() * 10000
        else: cost_y = 1.0

        if has_spread_x: cost_x = (df["SX"] / df["X"]).mean() * 10000
        else: cost_x = 1.0

        total_spread_cost = cost_y + cost_x

        kf = KalmanFilterReg(Q=1e-5, R=1e-3)
        betas, errors = [], []

        # Rolling Window State
        y_win, x_win = [], []

        for i in range(len(y)):
            y_win.append(y[i])
            x_win.append(x[i])
            if len(y_win) > 500: y_win.pop(0); x_win.pop(0)

            if len(y_win) < 10: mu_y, mu_x = y[i], x[i]
            else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)

            y_c = y[i] - mu_y
            x_c = x[i] - mu_x

            b, _ = kf.update(x_c, y_c)
            betas.append(b)
            errors.append(y_c - b * x_c)

        real_pnls = []
        gross_pnls = []
        in_pos = 0
        entry_beta, entry_y, entry_x = 0., 0., 0.
        trades = 0

        for i in range(500, len(y)):
            window = errors[i-500:i]
            mu, std = np.mean(window), np.std(window)
            if std < 1e-6: continue
            z = (errors[i] - mu) / std

            beta = betas[i-1]

            # THRESHOLD 1.5
            if in_pos == 0:
                if z > 1.5: in_pos = -1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
                elif z < -1.5: in_pos = 1; entry_beta=beta; entry_y=y[i]; entry_x=x[i]
            elif in_pos == 1:
                if z > 0.0 or z < -2.0:
                    gross = (y[i] - entry_y) - entry_beta*(x[i] - entry_x)
                    gross_bps = gross * 10000
                    net_bps = gross_bps - total_spread_cost

                    real_pnls.append(net_bps)
                    gross_pnls.append(gross_bps)
                    in_pos = 0; trades += 1
            elif in_pos == -1:
                if z < 0.0 or z > 2.0:
                    gross = -(y[i] - entry_y) + entry_beta*(x[i] - entry_x)
                    gross_bps = gross * 10000
                    net_bps = gross_bps - total_spread_cost

                    real_pnls.append(net_bps)
                    gross_pnls.append(gross_bps)
                    in_pos = 0; trades += 1

        if len(real_pnls) > 5:
            avg_pnl = np.mean(real_pnls)
            avg_gross = np.mean(gross_pnls)

            if avg_pnl > 0:
                return {
                    "y": y_sym, "x": x_sym,
                    "gross": avg_gross, "cost": total_spread_cost, "net": avg_pnl, "trades": trades
                }
        return None
    except: return None

if __name__ == "__main__":
    scan_full_universe()
