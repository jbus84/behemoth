#!/usr/bin/env python3
"""
Multi-hedge (basket) Kalman experiments on 15m data.
Compares baseline 2-leg vs basket hedges for MOM/REV trades.

Outputs:
 - data/analysis/m15_kalman_basket_summary.csv
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import numpy as np
import pandas as pd
import polars as pl

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from kalman_filter import KalmanFilterRegMulti
from metrics import sharpe_daily

DATA_DIR = "data/global_15m"
OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

# name, y_file, y_col, x_specs[(file, col, invert_log)]
BASKETS: List[dict] = [
    {
        "name": "EURUSD~GBPUSD",
        "y": ("EURUSD_15m.parquet", "close_EURUSD"),
        "x": [("GBPUSD_15m.parquet", "close_GBPUSD", False)],
    },
    {
        "name": "EURUSD~GBPUSD+USDCHF",
        "y": ("EURUSD_15m.parquet", "close_EURUSD"),
        "x": [
            ("GBPUSD_15m.parquet", "close_GBPUSD", False),
            ("USDCHF_15m.parquet", "close_USDCHF", False),
        ],
    },
    {
        "name": "EURUSD~GBPUSD+USDCAD",
        "y": ("EURUSD_15m.parquet", "close_EURUSD"),
        "x": [
            ("GBPUSD_15m.parquet", "close_GBPUSD", False),
            ("USDCAD_15m.parquet", "close_USDCAD", False),
        ],
    },
    {
        "name": "EURUSD~GBPUSD+USDCHF+USDCAD",
        "y": ("EURUSD_15m.parquet", "close_EURUSD"),
        "x": [
            ("GBPUSD_15m.parquet", "close_GBPUSD", False),
            ("USDCHF_15m.parquet", "close_USDCHF", False),
            ("USDCAD_15m.parquet", "close_USDCAD", False),
        ],
    },
    {
        "name": "EURUSD~GBPUSD+SPX",
        "y": ("EURUSD_15m.parquet", "close_EURUSD"),
        "x": [
            ("GBPUSD_15m.parquet", "close_GBPUSD", False),
            ("SPXUSD_15m.parquet", "close_SPXUSD", False),
        ],
    },
    {
        "name": "SPX~DAX",
        "y": ("SPXUSD_15m.parquet", "close_SPXUSD"),
        "x": [("GRXEUR_15m.parquet", "close_GRXEUR", False)],
    },
    {
        "name": "SPX~DAX+Nas",
        "y": ("SPXUSD_15m.parquet", "close_SPXUSD"),
        "x": [
            ("GRXEUR_15m.parquet", "close_GRXEUR", False),
            ("NSXUSD_15m.parquet", "close_NSXUSD", False),
        ],
    },
    {
        "name": "SPX~DAX+Dow",
        "y": ("SPXUSD_15m.parquet", "close_SPXUSD"),
        "x": [
            ("GRXEUR_15m.parquet", "close_GRXEUR", False),
            ("UDXUSD_15m.parquet", "close_UDXUSD", False),
        ],
    },
    {
        "name": "SPX~DAX+Nas+Dow",
        "y": ("SPXUSD_15m.parquet", "close_SPXUSD"),
        "x": [
            ("GRXEUR_15m.parquet", "close_GRXEUR", False),
            ("NSXUSD_15m.parquet", "close_NSXUSD", False),
            ("UDXUSD_15m.parquet", "close_UDXUSD", False),
        ],
    },
]


def _load_basket(
    y_file: str, y_col: str, x_specs: List[Tuple[str, str, bool]]
) -> pl.DataFrame:
    df = (
        pl.read_parquet(os.path.join(DATA_DIR, y_file))
        .select(["timestamp", y_col])
        .rename({y_col: "Y"})
    )
    for idx, (xf, xc, _) in enumerate(x_specs):
        xdf = (
            pl.read_parquet(os.path.join(DATA_DIR, xf))
            .select(["timestamp", xc])
            .rename({xc: f"X{idx}"})
        )
        df = df.join(xdf, on="timestamp", how="inner")
    df = df.sort("timestamp")
    df = df.filter(pl.col("timestamp").dt.year().is_between(2018, 2025))
    return df


def _compute_kalman_states_multi(y: np.ndarray, X: np.ndarray):
    k = X.shape[1]
    kf = KalmanFilterRegMulti(k, Q=1e-5, R=1e-3)
    betas = np.zeros((len(y), k))
    errors = np.zeros(len(y))

    for i in range(len(y)):
        if i < 10:
            mu_y = y[i]
            mu_x = X[i]
        else:
            start = max(0, i - 500)
            mu_y = float(np.mean(y[start:i]))
            mu_x = np.mean(X[start:i], axis=0)
        x_c = X[i] - mu_x
        y_c = y[i] - mu_y
        beta, _ = kf.update(x_c, y_c)
        betas[i] = beta
        errors[i] = y_c - float(np.dot(beta, x_c))

    # Return-Kalman (hedge beta proxy)
    kf_ret = KalmanFilterRegMulti(k, Q=1e-5, R=1e-3)
    ret_betas = np.zeros((len(y), k))
    if len(y) > 1:
        for i in range(1, len(y)):
            ry = y[i] - y[i - 1]
            rx = X[i] - X[i - 1]
            b_ret, _ = kf_ret.update(rx, ry)
            ret_betas[i] = b_ret
        ret_betas[0] = ret_betas[1]

    return betas, errors, ret_betas


def _compute_z_scores(errors: np.ndarray, window: int = 500) -> np.ndarray:
    z = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i - window : i]
        mu = float(np.mean(window_data))
        std = float(np.std(window_data))
        if std > 1e-6:
            z[i] = (errors[i] - mu) / std
    return z


def _exit_hit(strategy_type: str, direction: int, z: float) -> bool:
    if strategy_type == "MOM":
        if direction == 1:
            return z < 0 or z > STOP_LEVEL
        return z > 0 or z < -STOP_LEVEL
    if direction == 1:
        return z > 0 or z < -STOP_LEVEL
    return z < 0 or z > STOP_LEVEL


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnls: list[float], timestamps: list) -> dict:
    if not pnls:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    arr = np.asarray(pnls, dtype=float)
    return dict(
        trades=int(len(arr)),
        win_rate=float((arr > 0).mean() * 100.0),
        mean_pnl=float(arr.mean()),
        total_pnl=float(arr.sum()),
        max_dd=_max_dd(arr),
        sharpe=sharpe_daily(arr, timestamps),
    )


def _simulate_trades(
    y: np.ndarray,
    X: np.ndarray,
    z_scores: np.ndarray,
    betas_lvl: np.ndarray,
    betas_ret: np.ndarray,
    ts: np.ndarray,
):
    results = []
    n = len(y)
    for strat in ["MOM", "REV"]:
        last_entry = 0
        for i in range(500, n - 2):
            z = z_scores[i]
            if strat == "MOM":
                if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                    continue
                direction = 1 if z > 0 else -1
            else:
                if abs(z) < THRESH_REV or i - last_entry < MIN_GAP:
                    continue
                direction = -1 if z > 0 else 1

            end = min(i + MAX_HOLD, n - 1)
            exit_idx = end
            for j in range(i + 1, end + 1):
                if _exit_hit(strat, direction, z_scores[j]):
                    exit_idx = j
                    break

            d_y = np.diff(y[i : exit_idx + 1])
            d_x = np.diff(X[i : exit_idx + 1], axis=0)
            b_lvl = betas_lvl[i + 1 : exit_idx + 1]
            b_ret = betas_ret[i + 1 : exit_idx + 1]

            pnl_unhedged = float(np.sum(direction * d_y * 10000.0))
            pnl_level = float(np.sum(direction * (d_y - np.sum(b_lvl * d_x, axis=1)) * 10000.0))
            pnl_ret = float(np.sum(direction * (d_y - np.sum(b_ret * d_x, axis=1)) * 10000.0))

            results.append(
                {
                    "strategy_type": strat,
                    "pnl_unhedged": pnl_unhedged,
                    "pnl_level_beta": pnl_level,
                    "pnl_ret_beta": pnl_ret,
                    "exit_ts": ts[exit_idx],
                }
            )
            last_entry = i
    return results


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []

    for basket in BASKETS:
        name = basket["name"]
        y_file, y_col = basket["y"]
        x_specs = basket["x"]
        df = _load_basket(y_file, y_col, x_specs)

        ts = df["timestamp"].to_numpy()
        y = np.log(df["Y"].to_numpy())
        x_cols = []
        for idx, (_, _, invert) in enumerate(x_specs):
            series = np.log(df[f"X{idx}"].to_numpy())
            x_cols.append(-series if invert else series)
        X = np.vstack(x_cols).T

        betas, errors, ret_betas = _compute_kalman_states_multi(y, X)
        z_scores = _compute_z_scores(errors)

        trades = _simulate_trades(y, X, z_scores, betas, ret_betas, ts)
        for strat in ["MOM", "REV"]:
            for mode_key, mode_label in [
                ("pnl_unhedged", "unhedged"),
                ("pnl_level_beta", "level_beta"),
                ("pnl_ret_beta", "ret_beta"),
            ]:
                pnls = [t[mode_key] for t in trades if t["strategy_type"] == strat]
                tss = [t["exit_ts"] for t in trades if t["strategy_type"] == strat]
                stats = _metrics(pnls, tss)
                rows.append(
                    {
                        "basket": name,
                        "strategy_type": strat,
                        "hedge_mode": mode_label,
                        **stats,
                    }
                )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m15_kalman_basket_summary.csv"), index=False)
    print("Saved: data/analysis/m15_kalman_basket_summary.csv")


if __name__ == "__main__":
    main()
