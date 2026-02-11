#!/usr/bin/env python3
"""
Compare MOM baseline vs volatility targeting (M15).

Outputs:
- data/analysis/mom_vol_target_comparison.csv
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m15 as m15
from metrics import sharpe_daily
from risk_controls import conditional_vol_scale, vol_target_scale

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

VOL_WINDOW = 60
VOL_TARGET_Q = 0.5
VOL_HIGH_Q = 0.8
SCALE_CAP = 2.0
SCALE_FLOOR = 0.2


def _exit_hit(direction: int, z: float) -> bool:
    if direction == 1:
        return z < 0 or z > STOP_LEVEL
    return z > 0 or z < -STOP_LEVEL


def _trade_path(
    entry_idx: int,
    direction: int,
    y: np.ndarray,
    x: np.ndarray,
    z_scores: np.ndarray,
    active_leg: str,
) -> tuple[np.ndarray, int]:
    active = y if active_leg == "Y" else x
    d_active = []
    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end
    for i in range(entry_idx + 1, end + 1):
        d_active.append(active[i] - active[i - 1])
        if _exit_hit(direction, z_scores[i]):
            exit_idx = i
            break
    return np.asarray(d_active), exit_idx


def _rolling_vol(series: np.ndarray, window: int) -> np.ndarray:
    if len(series) < 2:
        return np.full(len(series), np.nan)
    r = np.diff(series)
    vol = pd.Series(r).rolling(window, min_periods=window).std().shift(1).to_numpy()
    out = np.full(len(series), np.nan)
    out[1:] = vol
    return out


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(trades: list[tuple[int, float]]) -> dict:
    if not trades:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, max_dd_pct=0.0, sharpe=0.0)
    df = pd.DataFrame(trades, columns=["ts", "pnl"]).sort_values("ts")
    pnl = df["pnl"].to_numpy()
    max_dd = _max_dd(pnl)
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=max_dd,
        max_dd_pct=float(max_dd / 100.0),
        sharpe=sharpe_daily(pnl, df["ts"].to_numpy()),
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    trades_base: list[tuple[int, float]] = []
    trades_vol: list[tuple[int, float]] = []
    trades_cond: list[tuple[int, float]] = []
    scales_vol = []
    scales_cond = []

    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

        vol_y = _rolling_vol(y, VOL_WINDOW)
        vol_x = _rolling_vol(x, VOL_WINDOW)

        years = pd.to_datetime(ts, unit="ns", utc=True, errors="coerce").year
        train_mask = years <= 2023

        vol_y_train = vol_y[train_mask & np.isfinite(vol_y)]
        vol_x_train = vol_x[train_mask & np.isfinite(vol_x)]
        target_vol_y = float(np.nanquantile(vol_y_train, VOL_TARGET_Q)) if len(vol_y_train) else np.nan
        target_vol_x = float(np.nanquantile(vol_x_train, VOL_TARGET_Q)) if len(vol_x_train) else np.nan
        high_vol_y = float(np.nanquantile(vol_y_train, VOL_HIGH_Q)) if len(vol_y_train) else np.nan
        high_vol_x = float(np.nanquantile(vol_x_train, VOL_HIGH_Q)) if len(vol_x_train) else np.nan

        last_entry = 0
        for i in range(500, len(y) - 2):
            z = z_scores[i]
            beta = betas[i]

            if beta < 0.98:
                active_leg = "Y"
                vol_entry = vol_y[i]
                target_vol = target_vol_y
                high_vol = high_vol_y
            elif beta > 1.02:
                active_leg = "X"
                vol_entry = vol_x[i]
                target_vol = target_vol_x
                high_vol = high_vol_x
            else:
                continue

            if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                continue

            direction = 1 if z > 0 else -1
            d_active, exit_idx = _trade_path(i, direction, y, x, z_scores, active_leg)
            pnl_path = direction * d_active * 10000.0
            pnl = float(np.sum(pnl_path))
            exit_ts = int(ts[exit_idx])

            scale = vol_target_scale(vol_entry, target_vol, cap=SCALE_CAP, floor=SCALE_FLOOR)
            scale_cond = conditional_vol_scale(
                vol_entry, target_vol, high_vol, cap=SCALE_CAP, floor=SCALE_FLOOR
            )

            trades_base.append((exit_ts, pnl))
            trades_vol.append((exit_ts, pnl * scale))
            trades_cond.append((exit_ts, pnl * scale_cond))
            scales_vol.append(scale)
            scales_cond.append(scale_cond)

            last_entry = i

    rows = []
    for label, trades, scales in [
        ("baseline", trades_base, [1.0] * len(trades_base)),
        ("vol_target", trades_vol, scales_vol),
        ("vol_target_conditional", trades_cond, scales_cond),
    ]:
        stats = _metrics(trades)
        scales_arr = np.asarray(scales, dtype=float)
        rows.append(
            {
                "variant": label,
                **stats,
                "vol_scale_mean": float(np.mean(scales_arr)) if len(scales_arr) else 0.0,
                "vol_scale_p95": float(np.percentile(scales_arr, 95)) if len(scales_arr) else 0.0,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "mom_vol_target_comparison.csv"), index=False)
    print("Saved: data/analysis/mom_vol_target_comparison.csv")


if __name__ == "__main__":
    main()
