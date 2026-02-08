#!/usr/bin/env python3
"""
Build MFE/MAE dataset for H1 meta signals.
Outputs: data/analysis/mfe_mae_h1.csv
"""

import os
import numpy as np
import polars as pl
from datetime import datetime

from build_meta_dataset_v3_h1 import (
    PAIRS,
    load_pair_data,
    compute_kalman_states,
    compute_z_scores,
    compute_features_at_entry,
)

OUT_DIR = "data/analysis"
OUT_PATH = os.path.join(OUT_DIR, "mfe_mae_h1.csv")


def simulate_trade_with_mfe_mae(entry_idx, direction, strategy_type, y, x, z_scores, active_asset, thresh=1.5, stop=3.5):
    prices = y if active_asset == 'Y' else x
    entry_price = prices[entry_idx]

    mfe = -1e9
    mae = 1e9

    for i in range(entry_idx + 1, min(entry_idx + 500, len(z_scores))):
        z = z_scores[i]
        curr_price = prices[i]
        pnl = (curr_price - entry_price) * 10000 * (1 if direction == 1 else -1)

        if pnl > mfe:
            mfe = pnl
        if pnl < mae:
            mae = pnl

        if strategy_type == 'MOM':
            if direction == 1:  # Long
                if z < 0:
                    return pnl, i - entry_idx, 'LOSS_REV', mfe, mae
                elif z > stop:
                    return pnl, i - entry_idx, 'WIN_MOM', mfe, mae
            else:  # Short
                if z > 0:
                    return pnl, i - entry_idx, 'LOSS_REV', mfe, mae
                elif z < -stop:
                    return pnl, i - entry_idx, 'WIN_MOM', mfe, mae
        else:  # REVERSION
            if direction == 1:  # Long
                if z > 0:
                    return pnl, i - entry_idx, 'WIN_REV', mfe, mae
                elif z < -stop:
                    return pnl, i - entry_idx, 'LOSS_MOM', mfe, mae
            else:  # Short
                if z < 0:
                    return pnl, i - entry_idx, 'WIN_REV', mfe, mae
                elif z > stop:
                    return pnl, i - entry_idx, 'LOSS_MOM', mfe, mae

    # Timeout
    curr_price = prices[min(entry_idx + 499, len(prices) - 1)]
    pnl = (curr_price - entry_price) * 10000 * (1 if direction == 1 else -1)

    if pnl > mfe:
        mfe = pnl
    if pnl < mae:
        mae = pnl

    return pnl, 500, 'TIMEOUT', mfe, mae


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("--- BUILDING MFE/MAE DATASET (H1) ---")

    thresh = 1.5
    stop_level = 3.5

    all_events = []

    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        betas, errors, ret_betas = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)

        print(f"Processing {name} | bars={len(y)}")

        last_entry_mom = 0
        last_entry_rev = 0
        min_gap = 20

        for i in range(500, len(y) - 500):
            z = z_scores[i]
            beta = betas[i]

            if beta < 0.98:
                active_asset = 'Y'
            elif beta > 1.02:
                active_asset = 'X'
            else:
                continue

            if abs(z) < thresh:
                continue

            features = compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts)

            # MOM
            if i - last_entry_mom >= min_gap:
                mom_dir = 1 if z > thresh else -1
                pnl, duration, outcome, mfe, mae = simulate_trade_with_mfe_mae(
                    i, mom_dir, 'MOM', y, x, z_scores, active_asset, thresh, stop_level
                )

                row = {
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(str(ts[i])[:4]),
                    "strategy_type": "MOM",
                    "active_leg": active_asset,
                    "side": "LONG" if mom_dir == 1 else "SHORT",
                    "outcome": outcome,
                    "pnl_bps": round(pnl, 2),
                    "duration_bars": duration,
                    "mfe_bps": round(mfe, 2),
                    "mae_bps": round(mae, 2),
                    **features,
                }
                all_events.append(row)
                last_entry_mom = i

            # REV
            if i - last_entry_rev >= min_gap:
                rev_dir = -1 if z > thresh else 1
                pnl, duration, outcome, mfe, mae = simulate_trade_with_mfe_mae(
                    i, rev_dir, 'REV', y, x, z_scores, active_asset, thresh, stop_level
                )

                row = {
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(str(ts[i])[:4]),
                    "strategy_type": "REV",
                    "active_leg": active_asset,
                    "side": "LONG" if rev_dir == 1 else "SHORT",
                    "outcome": outcome,
                    "pnl_bps": round(pnl, 2),
                    "duration_bars": duration,
                    "mfe_bps": round(mfe, 2),
                    "mae_bps": round(mae, 2),
                    **features,
                }
                all_events.append(row)
                last_entry_rev = i

    print(f"Saving {len(all_events)} events to {OUT_PATH}")
    pl.DataFrame(all_events).write_csv(OUT_PATH)


if __name__ == "__main__":
    main()
