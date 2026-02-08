#!/usr/bin/env python3
"""
Diagnostics for 30m hedge behavior.
Runs:
1) Beta sanity (return vs level)
2) Hedge variants (return, level, clipped, filtered)
3) Risk stats (mean/std/sharpe + DD)

Outputs:
- data/analysis/m30_hedge_diagnostics_summary.csv
- data/analysis/m30_hedge_beta_sanity.csv
"""

from __future__ import annotations

import os
from collections import defaultdict

import numpy as np
import pandas as pd

import sys
sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m30 as m30

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

VARIANTS = [
    {"name": "unhedged", "beta_kind": None, "clip": None, "filter": None},
    {"name": "ret_beta", "beta_kind": "return", "clip": None, "filter": None},
    {"name": "ret_beta_clip5", "beta_kind": "return", "clip": 5.0, "filter": None},
    {"name": "ret_beta_clip10", "beta_kind": "return", "clip": 10.0, "filter": None},
    {"name": "ret_beta_filter0.2", "beta_kind": "return", "clip": 10.0, "filter": 0.2},
    {"name": "level_beta", "beta_kind": "level", "clip": 10.0, "filter": None},
    {"name": "ret_beta_mm_0.5_2.0", "beta_kind": "return", "clip": 10.0, "filter": None, "mm_min": 0.5, "mm_max": 2.0},
    {"name": "ret_beta_mm_0.7_1.5", "beta_kind": "return", "clip": 10.0, "filter": None, "mm_min": 0.7, "mm_max": 1.5},
    {"name": "ret_beta_mm_0.8_1.2", "beta_kind": "return", "clip": 10.0, "filter": None, "mm_min": 0.8, "mm_max": 1.2},
]


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _sharpe(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    std = float(np.std(pnl, ddof=1)) if len(pnl) > 1 else 0.0
    if std <= 1e-12:
        return 0.0
    return float(np.mean(pnl) / std)


def _exit_hit(strategy_type: str, direction: int, z: float) -> bool:
    if strategy_type == "MOM":
        if direction == 1:
            return z < 0 or z > STOP_LEVEL
        return z > 0 or z < -STOP_LEVEL
    # REV
    if direction == 1:
        return z > 0 or z < -STOP_LEVEL
    return z < 0 or z > STOP_LEVEL


def _hedge_ratio(active_leg: str, beta: float) -> float:
    if active_leg == "Y":
        return beta
    if abs(beta) < 1e-6:
        return 0.0
    return 1.0 / beta


def _collect_trade_path(
    entry_idx: int,
    direction: int,
    strategy_type: str,
    y: np.ndarray,
    x: np.ndarray,
    z_scores: np.ndarray,
    ret_betas: np.ndarray,
    level_betas: np.ndarray,
    mismatch: np.ndarray,
    active_leg: str,
    month_arr: np.ndarray,
) -> dict:
    active = y if active_leg == "Y" else x
    other = x if active_leg == "Y" else y

    deltas_active = []
    deltas_other = []
    betas_ret = []
    betas_lvl = []
    mismatches = []
    months = []

    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end

    for i in range(entry_idx + 1, end + 1):
        deltas_active.append(active[i] - active[i - 1])
        deltas_other.append(other[i] - other[i - 1])
        betas_ret.append(ret_betas[i])
        betas_lvl.append(level_betas[i])
        mismatches.append(mismatch[i])
        months.append(month_arr[i])

        if _exit_hit(strategy_type, direction, z_scores[i]):
            exit_idx = i
            break

    return {
        "exit_idx": exit_idx,
        "d_active": np.asarray(deltas_active),
        "d_other": np.asarray(deltas_other),
        "betas_ret": np.asarray(betas_ret),
        "betas_lvl": np.asarray(betas_lvl),
        "mismatch": np.asarray(mismatches),
        "months": months,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    trade_rows = defaultdict(list)
    exposure_rows = defaultdict(list)
    clip_counts = defaultdict(int)
    total_counts = defaultdict(int)
    mismatch_skip_counts = defaultdict(int)
    mismatch_total_counts = defaultdict(int)
    beta_store = defaultdict(lambda: {"ret": [], "lvl": []})

    for name, fx, fy, cx, cy, _, _ in m30.PAIRS:
        df = m30.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        month_arr = pd.to_datetime(ts, unit="ns", utc=True, errors="coerce").strftime("%Y-%m").to_numpy()

        betas, errors, ret_betas = m30.compute_kalman_states(y, x)
        sig_beta_lb = pd.Series(betas).rolling(500, min_periods=2).mean().shift(1).fillna(betas[0]).to_numpy()
        hedge_beta_lb = pd.Series(ret_betas).rolling(500, min_periods=2).mean().shift(1).fillna(ret_betas[0]).to_numpy()
        mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
        mismatch = np.clip(mismatch, -10.0, 10.0)
        z_scores = m30.compute_z_scores(errors)

        last_entry_mom = 0
        last_entry_rev = 0

        for i in range(500, len(y) - 2):
            z = z_scores[i]
            beta = betas[i]

            if beta < 0.98:
                active_leg = "Y"
            elif beta > 1.02:
                active_leg = "X"
            else:
                continue

            # MOM
            if abs(z) >= THRESH_MOM and i - last_entry_mom >= MIN_GAP:
                direction = 1 if z > 0 else -1
                path = _collect_trade_path(i, direction, "MOM", y, x, z_scores, ret_betas, betas, mismatch, active_leg, month_arr)
                last_entry_mom = i
                _process_trade(
                    trade_rows,
                    exposure_rows,
                    clip_counts,
                    total_counts,
                    mismatch_skip_counts,
                    mismatch_total_counts,
                    beta_store,
                    "MOM",
                    active_leg,
                    direction,
                    ts[i],
                    month_arr[i],
                    path,
                )

            # REV
            if abs(z) >= THRESH_REV and i - last_entry_rev >= MIN_GAP:
                direction = -1 if z > 0 else 1
                path = _collect_trade_path(i, direction, "REV", y, x, z_scores, ret_betas, betas, mismatch, active_leg, month_arr)
                last_entry_rev = i
                _process_trade(
                    trade_rows,
                    exposure_rows,
                    clip_counts,
                    total_counts,
                    mismatch_skip_counts,
                    mismatch_total_counts,
                    beta_store,
                    "REV",
                    active_leg,
                    direction,
                    ts[i],
                    month_arr[i],
                    path,
                )

    # Summary
    summary_rows = []
    for (strat, variant), pnls in trade_rows.items():
        pnl = np.asarray(pnls, dtype=float)
        stats = {
            "strategy_type": strat,
            "variant": variant,
            "trades": int(len(pnl)),
            "win_rate": float((pnl > 0).mean() * 100.0) if len(pnl) else 0.0,
            "mean_pnl": float(pnl.mean()) if len(pnl) else 0.0,
            "std_pnl": float(pnl.std(ddof=1)) if len(pnl) > 1 else 0.0,
            "sharpe": _sharpe(pnl),
            "total_pnl": float(pnl.sum()) if len(pnl) else 0.0,
            "max_dd": _max_dd(pnl),
        }
        exp = np.asarray(exposure_rows[(strat, variant)], dtype=float)
        stats["mean_abs_exposure"] = float(np.mean(exp)) if len(exp) else 0.0
        stats["p90_abs_exposure"] = float(np.percentile(exp, 90)) if len(exp) else 0.0
        stats["p99_abs_exposure"] = float(np.percentile(exp, 99)) if len(exp) else 0.0
        if total_counts[(strat, variant)] > 0:
            stats["clip_rate"] = clip_counts[(strat, variant)] / total_counts[(strat, variant)]
        else:
            stats["clip_rate"] = 0.0
        if mismatch_total_counts[(strat, variant)] > 0:
            stats["mismatch_skip_rate"] = mismatch_skip_counts[(strat, variant)] / mismatch_total_counts[(strat, variant)]
        else:
            stats["mismatch_skip_rate"] = 0.0
        summary_rows.append(stats)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(os.path.join(OUT_DIR, "m30_hedge_diagnostics_summary.csv"), index=False)

    # Beta sanity
    sanity_rows = []
    for strat in ["MOM", "REV"]:
        for kind in ["ret", "lvl"]:
            arr = np.asarray(beta_store[strat][kind], dtype=float)
            if len(arr) == 0:
                continue
            sanity_rows.append(
                {
                    "strategy_type": strat,
                    "beta_kind": kind,
                    "mean": float(np.mean(arr)),
                    "median": float(np.median(arr)),
                    "p10": float(np.percentile(arr, 10)),
                    "p90": float(np.percentile(arr, 90)),
                    "pct_neg": float((arr < 0).mean() * 100.0),
                    "pct_abs_lt_0.2": float((np.abs(arr) < 0.2).mean() * 100.0),
                    "pct_abs_gt_5": float((np.abs(arr) > 5).mean() * 100.0),
                    "pct_abs_gt_10": float((np.abs(arr) > 10).mean() * 100.0),
                }
            )

    sanity = pd.DataFrame(sanity_rows)
    sanity.to_csv(os.path.join(OUT_DIR, "m30_hedge_beta_sanity.csv"), index=False)

    print("Saved:")
    print("- data/analysis/m30_hedge_diagnostics_summary.csv")
    print("- data/analysis/m30_hedge_beta_sanity.csv")


def _process_trade(
    trade_rows: dict,
    exposure_rows: dict,
    clip_counts: dict,
    total_counts: dict,
    mismatch_skip_counts: dict,
    mismatch_total_counts: dict,
    beta_store: dict,
    strat: str,
    active_leg: str,
    direction: int,
    entry_ts: int,
    entry_month: str,
    path: dict,
) -> None:
    d_active = path["d_active"]
    d_other = path["d_other"]
    betas_ret = path["betas_ret"]
    betas_lvl = path["betas_lvl"]
    mismatch = path["mismatch"]

    # beta sanity: collect all betas used within trades
    beta_store[strat]["ret"].extend(betas_ret.tolist())
    beta_store[strat]["lvl"].extend(betas_lvl.tolist())

    for variant in VARIANTS:
        name = variant["name"]
        beta_kind = variant["beta_kind"]
        clip = variant["clip"]
        filt = variant["filter"]

        if filt is not None:
            entry_beta = betas_ret[0] if beta_kind in (None, "return") else betas_lvl[0]
            if abs(entry_beta) < filt:
                continue

        if beta_kind is None:
            pnl = direction * d_active * 10000.0
        else:
            betas = betas_ret if beta_kind == "return" else betas_lvl
            ratio = np.array([_hedge_ratio(active_leg, b) for b in betas], dtype=float)
            mm_min = variant.get("mm_min")
            mm_max = variant.get("mm_max")
            if mm_min is not None and mm_max is not None:
                mask = (np.abs(mismatch) >= mm_min) & (np.abs(mismatch) <= mm_max)
                mismatch_total_counts[(strat, name)] += len(mask)
                mismatch_skip_counts[(strat, name)] += int(np.sum(~mask))
                ratio = np.where(mask, ratio, 0.0)
            if clip is not None:
                clipped = np.clip(ratio, -clip, clip)
                clip_counts[(strat, name)] += int(np.sum(np.abs(clipped) >= clip))
                ratio = clipped
            total_counts[(strat, name)] += len(ratio)
            pnl = direction * (d_active - ratio * d_other) * 10000.0

        trade_rows[(strat, name)].append(float(np.sum(pnl)))
        exposure_rows[(strat, name)].extend(np.abs(pnl).tolist())


if __name__ == "__main__":
    main()
