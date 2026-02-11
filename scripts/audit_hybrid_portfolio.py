
import polars as pl
import numpy as np
import os
from datetime import datetime, timezone
from kalman_filter import KalmanFilterReg

DATA_DIR_H4 = "data/global_4h"
DATA_DIR_H1 = "data/global_1h"

PAIRS = [
    ("EURUSD", "EURJPY", "Euro/Yen"),
    ("EURUSD", "AUDUSD", "Euro/Aussie"),
    ("USDCHF", "AUDUSD", "Swiss/Aussie"),
    ("GBPUSD", "USDCAD", "Cable/Loonie"),
]

def audit_hybrid():
    print("--- HYBRID PORTFOLIO AUDIT (FX REJECTS) ---")

    agg_h4 = {}
    agg_hyb = {}

    years = range(2018, 2026)

    print("\n| Pair | H4 Total | Hybrid Total | Diff |")
    print("|---|---|---|---|")

    grand_total_h4 = 0
    grand_total_hyb = 0

    for y_sym, x_sym, label in PAIRS:
        # --- 1. RUN H4 (Z=1.5) ---
        p_y_h4 = os.path.join(DATA_DIR_H4, f"{y_sym}_4h.parquet")
        p_x_h4 = os.path.join(DATA_DIR_H4, f"{x_sym}_4h.parquet")
        if not os.path.exists(p_y_h4): continue

        df_h4 = pl.read_parquet(p_y_h4).rename({f"close_{y_sym}": "Y"}).join(
                pl.read_parquet(p_x_h4).rename({f"close_{x_sym}": "X"}), on="timestamp", how="inner").sort("timestamp")

        pnl_h4 = calculate_pnl(df_h4, z_thresh=1.5, stop=3.5, label="H4")

        # --- 2. RUN H1 (Z=2.0) ---
        p_y_h1 = os.path.join(DATA_DIR_H1, f"{y_sym}_1h.parquet")
        p_x_h1 = os.path.join(DATA_DIR_H1, f"{x_sym}_1h.parquet")
        df_h1 = pl.read_parquet(p_y_h1).rename({f"close_{y_sym}": "Y"}).join(
                pl.read_parquet(p_x_h1).rename({f"close_{x_sym}": "X"}), on="timestamp", how="inner").sort("timestamp")

        pnl_h1 = calculate_pnl(df_h1, z_thresh=2.0, stop=3.5, label="H1")

        # --- 3. COMBINE ---
        pair_h4_total = 0
        pair_hyb_total = 0

        for yr in years:
            res_h4 = pnl_h4.get(yr, 0)
            res_h1 = pnl_h1.get(yr, 0)

            hybrid_res = (0.8 * res_h4) + (0.2 * res_h1)

            agg_h4[yr] = agg_h4.get(yr, 0) + res_h4
            agg_hyb[yr] = agg_hyb.get(yr, 0) + hybrid_res

            pair_h4_total += res_h4
            pair_hyb_total += hybrid_res

        print(f"| {label} | {pair_h4_total:.0f} | {pair_hyb_total:.0f} | {pair_hyb_total-pair_h4_total:+.0f} |")

        grand_total_h4 += pair_h4_total
        grand_total_hyb += pair_hyb_total

    print(f"| **GRAND TOTAL** | **{grand_total_h4:.0f}** | **{grand_total_hyb:.0f}** | **{grand_total_hyb-grand_total_h4:+.0f}** |")

    # Overall Yearly Breakdown
    print("\n| Year | Portfolio H4 | Portfolio Hybrid | Diff |")
    print("|---|---|---|---|")
    for yr in years:
        h4 = agg_h4.get(yr, 0)
        hyb = agg_hyb.get(yr, 0)
        print(f"| {yr} | {h4:.0f} | {hyb:.0f} | {hyb-h4:+.0f} |")


def calculate_pnl(df, z_thresh, stop, label):
    y_log = np.log(df["Y"].to_numpy())
    x_log = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()

    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas, errors = [], []
    y_win, x_win = [], []

    for i in range(len(y_log)):
        y_win.append(y_log[i]); x_win.append(x_log[i])
        if len(y_win)>500: y_win.pop(0); x_win.pop(0)
        if len(y_win) < 10: mu_y, mu_x = y_log[i], x_log[i]
        else: mu_y, mu_x = np.mean(y_win), np.mean(x_win)
        b, _ = kf.update(x_log[i]-mu_x, y_log[i]-mu_y)
        betas.append(b)
        errors.append((y_log[i]-mu_y) - b*(x_log[i]-mu_x))

    results = {}
    in_pos = 0
    entry_beta, entry_y, entry_x = 0., 0., 0.
    cost_bps = 9.0

    for i in range(500, len(y_log)):
        dt = ts[i]
        yr = dt.astype('datetime64[Y]').astype(int) + 1970

        window = errors[i-500:i]
        mu, std = np.mean(window), np.std(window)
        if std < 1e-6: continue
        z = (errors[i] - mu) / std

        pnl = 0.0

        if in_pos == 0:
            if z > z_thresh: in_pos = -1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
            elif z < -z_thresh: in_pos = 1; entry_beta=betas[i-1]; entry_y=y_log[i]; entry_x=x_log[i]
        elif in_pos == 1:
            if z > 0.0: # Win
                gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0
            elif z < -stop: # Stop
                gross = (y_log[i]-entry_y) - entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0
        elif in_pos == -1:
            if z < 0.0: # Win
                gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0
            elif z > stop: # Stop
                gross = -(y_log[i]-entry_y) + entry_beta*(x_log[i]-entry_x)
                pnl = gross * 10000 - cost_bps
                in_pos = 0

        if yr not in results: results[yr] = 0.0
        results[yr] += pnl

    return results

if __name__ == "__main__":
    audit_hybrid()
