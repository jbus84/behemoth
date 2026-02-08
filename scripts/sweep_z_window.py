#!/usr/bin/env python3
"""
Sweep Z-score lookback windows and report trade counts + gross PnL.

Uses the same logic as the v3 dataset builders:
- Z-entry trigger: |Z| >= 1.5
- Z-stop: |Z| > 3.5
- Z0 crossing exit
- Timeout: 500 bars
- Active leg via beta thresholds (0.98/1.02)
- Min gap: 20 bars per strategy

Outputs:
- data/analysis/z_window_sweep_<bar>.csv
- docs/figures/z_window_sweep_<bar>.png
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import numpy as np
import polars as pl
import pandas as pd
import matplotlib.pyplot as plt

from kalman_filter import KalmanFilterReg


BAR_CONFIG = {
    "m5": {"data_dir": "data/global_5m", "suffix": "5m"},
    "m15": {"data_dir": "data/global_15m", "suffix": "15m"},
    "m30": {"data_dir": "data/global_30m", "suffix": "30m"},
    "h1": {"data_dir": "data/global_1h", "suffix": "1h"},
}

PAIRS_BASE = [
    ("EUR/GBP", "EURUSD", "GBPUSD", "close_EURUSD", "close_GBPUSD"),
    ("Gold/Oil", "BCOUSD", "XAUUSD", "close_BCOUSD", "close_XAUUSD"),
    ("Oil/Silver", "BCOUSD", "XAGUSD", "close_BCOUSD", "close_XAGUSD"),
    ("AUD/NZD", "NZDUSD", "AUDUSD", "close_NZDUSD", "close_AUDUSD"),
    ("CAC/NZD", "NZDUSD", "FRXEUR", "close_NZDUSD", "close_FRXEUR"),
    ("Gold/Silver", "XAUUSD", "XAGUSD", "close_XAUUSD", "close_XAGUSD"),
    ("SPX/DAX", "SPXUSD", "GRXEUR", "close_SPXUSD", "close_GRXEUR"),
    ("SPX/CAC", "SPXUSD", "FRXEUR", "close_SPXUSD", "close_FRXEUR"),
    ("SPX/FTSE", "SPXUSD", "UKXGBP", "close_SPXUSD", "close_UKXGBP"),
    ("SPX/Nikkei", "SPXUSD", "JPXJPY", "close_SPXUSD", "close_JPXJPY"),
    ("SPX/HK", "SPXUSD", "HKXHKD", "close_SPXUSD", "close_HKXHKD"),
    ("SPX/Dow", "SPXUSD", "UDXUSD", "close_SPXUSD", "close_UDXUSD"),
    ("SPX/Nas", "SPXUSD", "NSXUSD", "close_SPXUSD", "close_NSXUSD"),
    ("AUD/CAD", "AUDUSD", "USDCAD", "close_AUDUSD", "close_USDCAD"),
    ("EUR/CHF", "EURUSD", "USDCHF", "close_EURUSD", "close_USDCHF"),
    ("EUR/JPY", "EURUSD", "USDJPY", "close_EURUSD", "close_USDJPY"),
    ("GBP/JPY", "GBPUSD", "USDJPY", "close_GBPUSD", "close_USDJPY"),
    ("CHF/JPY", "USDCHF", "USDJPY", "close_USDCHF", "close_USDJPY"),
    ("EUR/AUD", "EURUSD", "AUDUSD", "close_EURUSD", "close_AUDUSD"),
    ("GBP/AUD", "GBPUSD", "AUDUSD", "close_GBPUSD", "close_AUDUSD"),
    ("GBP/CAD", "GBPUSD", "USDCAD", "close_GBPUSD", "close_USDCAD"),
    ("NZD/CAD", "NZDUSD", "USDCAD", "close_NZDUSD", "close_USDCAD"),
]

Z_ENTRY_MOM = 1.5
Z_ENTRY_REV = 2.5
Z_STOP = 3.5
MIN_GAP = 20
TIMEOUT = 500


def _load_pair_data(data_dir: str, suffix: str, fx: str, fy: str, cx: str, cy: str) -> pl.DataFrame | None:
    try:
        p_x = Path(data_dir) / f"{fx}_{suffix}.parquet"
        p_y = Path(data_dir) / f"{fy}_{suffix}.parquet"
        df_x = pl.read_parquet(p_x).rename({cx: "X"})
        df_y = pl.read_parquet(p_y).rename({cy: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {fx}/{fy}: {e}")
        return None


def compute_kalman_states(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = np.zeros(len(y))
    errors = np.zeros(len(y))

    for i in range(len(y)):
        if i < 10:
            mu_y, mu_x = y[i], x[i]
        else:
            mu_y = np.mean(y[max(0, i - 500) : i])
            mu_x = np.mean(x[max(0, i - 500) : i])
        b, _ = kf.update(x[i] - mu_x, y[i] - mu_y)
        betas[i] = b
        errors[i] = (y[i] - mu_y) - b * (x[i] - mu_x)

    return betas, errors


def compute_z_scores(errors: np.ndarray, window: int) -> np.ndarray:
    z_scores = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i - window : i]
        mu, std = np.mean(window_data), np.std(window_data)
        if std > 1e-6:
            z_scores[i] = (errors[i] - mu) / std
    return z_scores


def simulate_trade(
    entry_idx: int,
    direction: int,
    strategy_type: str,
    y: np.ndarray,
    x: np.ndarray,
    z_scores: np.ndarray,
    active_asset: str,
) -> float:
    prices = y if active_asset == "Y" else x
    entry_price = prices[entry_idx]

    for i in range(entry_idx + 1, min(entry_idx + TIMEOUT, len(z_scores))):
        z = z_scores[i]
        curr_price = prices[i]

        if strategy_type == "MOM":
            if direction == 1:  # Long
                if z < 0:
                    return (curr_price - entry_price) * 10000
                if z > Z_STOP:
                    return (curr_price - entry_price) * 10000
            else:  # Short
                if z > 0:
                    return -(curr_price - entry_price) * 10000
                if z < -Z_STOP:
                    return -(curr_price - entry_price) * 10000
        else:  # REV
            if direction == 1:  # Long
                if z > 0:
                    return (curr_price - entry_price) * 10000
                if z < -Z_STOP:
                    return (curr_price - entry_price) * 10000
            else:  # Short
                if z < 0:
                    return -(curr_price - entry_price) * 10000
                if z > Z_STOP:
                    return -(curr_price - entry_price) * 10000

    # Timeout
    curr_price = prices[min(entry_idx + TIMEOUT - 1, len(prices) - 1)]
    if direction == 1:
        return (curr_price - entry_price) * 10000
    return -(curr_price - entry_price) * 10000


def sweep(bar: str, windows: List[int]) -> pd.DataFrame:
    cfg = BAR_CONFIG[bar]
    data_dir = cfg["data_dir"]
    suffix = cfg["suffix"]

    results: Dict[int, Dict[str, float]] = {w: {"mom_trades": 0, "mom_pnl": 0.0, "rev_trades": 0, "rev_pnl": 0.0} for w in windows}

    for name, fx, fy, cx, cy in PAIRS_BASE:
        df = _load_pair_data(data_dir, suffix, fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())

        betas, errors = compute_kalman_states(y, x)

        for w in windows:
            z_scores = compute_z_scores(errors, window=w)
            start_idx = max(500, w)
            last_entry_mom = 0
            last_entry_rev = 0

            for i in range(start_idx, len(y) - TIMEOUT):
                z = z_scores[i]
                if abs(z) < min(Z_ENTRY_MOM, Z_ENTRY_REV):
                    continue

                beta = betas[i]
                if beta < 0.98:
                    active = "Y"
                elif beta > 1.02:
                    active = "X"
                else:
                    continue

                if i - last_entry_mom >= MIN_GAP and abs(z) >= Z_ENTRY_MOM:
                    mom_dir = 1 if z > 0 else -1
                    pnl = simulate_trade(i, mom_dir, "MOM", y, x, z_scores, active)
                    results[w]["mom_trades"] += 1
                    results[w]["mom_pnl"] += pnl
                    last_entry_mom = i

                if i - last_entry_rev >= MIN_GAP and abs(z) >= Z_ENTRY_REV:
                    rev_dir = -1 if z > 0 else 1
                    pnl = simulate_trade(i, rev_dir, "REV", y, x, z_scores, active)
                    results[w]["rev_trades"] += 1
                    results[w]["rev_pnl"] += pnl
                    last_entry_rev = i

    rows = []
    for w in windows:
        mom_trades = results[w]["mom_trades"]
        rev_trades = results[w]["rev_trades"]
        mom_pnl = results[w]["mom_pnl"]
        rev_pnl = results[w]["rev_pnl"]
        rows.append(
            {
                "z_window": w,
                "mom_trades": mom_trades,
                "mom_gross_total_bps": mom_pnl,
                "mom_gross_mean_bps": mom_pnl / mom_trades if mom_trades else 0.0,
                "rev_trades": rev_trades,
                "rev_gross_total_bps": rev_pnl,
                "rev_gross_mean_bps": rev_pnl / rev_trades if rev_trades else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("z_window")


def plot(df: pd.DataFrame, bar: str, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    axes[0].plot(df["z_window"], df["mom_trades"], marker="o", label="MOM")
    axes[0].plot(df["z_window"], df["rev_trades"], marker="o", label="REV")
    axes[0].set_title(f"{bar.upper()} trades vs Z-window")
    axes[0].set_xlabel("Z window (bars)")
    axes[0].set_ylabel("Trade count")
    axes[0].legend()

    axes[1].plot(df["z_window"], df["mom_gross_total_bps"], marker="o", label="MOM")
    axes[1].plot(df["z_window"], df["rev_gross_total_bps"], marker="o", label="REV")
    axes[1].set_title(f"{bar.upper()} gross PnL vs Z-window")
    axes[1].set_xlabel("Z window (bars)")
    axes[1].set_ylabel("Gross PnL (bps)")
    axes[1].legend()

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=["m5", "m15", "m30", "h1"], required=True)
    parser.add_argument("--windows", default="100,250,500,750,1000")
    args = parser.parse_args()

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]

    df = sweep(args.bar, windows)
    out_csv = Path("data/analysis") / f"z_window_sweep_{args.bar}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    out_fig = Path("docs/figures") / f"z_window_sweep_{args.bar}.png"
    plot(df, args.bar, out_fig)

    print(f"Saved:\n- {out_csv}\n- {out_fig}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
