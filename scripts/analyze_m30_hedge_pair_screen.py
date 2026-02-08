#!/usr/bin/env python3
"""
Pair-level hedge diagnostics for 30m data.
Compares unhedged vs hedged (return beta / level beta / mismatch-gated).

Outputs:
- data/analysis/m30_hedge_pair_summary.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3_m30 as m30

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500
HEDGE_CLIP = 10.0

VARIANTS = [
    {"name": "unhedged", "beta_kind": None, "mm_min": None, "mm_max": None},
    {"name": "ret_beta", "beta_kind": "return", "mm_min": None, "mm_max": None},
    {"name": "level_beta", "beta_kind": "level", "mm_min": None, "mm_max": None},
    {"name": "ret_beta_mm_0.7_1.5", "beta_kind": "return", "mm_min": 0.7, "mm_max": 1.5},
]


def _max_dd(pnl: np.ndarray) -> float:
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


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
        ratio = beta
    else:
        ratio = 0.0 if abs(beta) < 1e-6 else 1.0 / beta
    return float(np.clip(ratio, -HEDGE_CLIP, HEDGE_CLIP))


def _trade_path(
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
) -> dict:
    active = y if active_leg == "Y" else x
    other = x if active_leg == "Y" else y

    d_active = []
    d_other = []
    betas_ret = []
    betas_lvl = []
    mm = []

    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end

    for i in range(entry_idx + 1, end + 1):
        d_active.append(active[i] - active[i - 1])
        d_other.append(other[i] - other[i - 1])
        betas_ret.append(ret_betas[i])
        betas_lvl.append(level_betas[i])
        mm.append(mismatch[i])

        if _exit_hit(strategy_type, direction, z_scores[i]):
            exit_idx = i
            break

    return {
        "exit_idx": exit_idx,
        "d_active": np.asarray(d_active),
        "d_other": np.asarray(d_other),
        "betas_ret": np.asarray(betas_ret),
        "betas_lvl": np.asarray(betas_lvl),
        "mismatch": np.asarray(mm),
    }


def _calc_metrics(pnl: np.ndarray, exposures: list[float]) -> dict:
    if len(pnl) == 0:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, mean_abs_exposure=0.0)
    return dict(
        trades=int(len(pnl)),
        win_rate=float((pnl > 0).mean() * 100.0),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=_max_dd(pnl),
        mean_abs_exposure=float(np.mean(exposures)) if exposures else 0.0,
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []

    for name, fx, fy, cx, cy, _, _ in m30.PAIRS:
        df = m30.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        betas, errors, ret_betas = m30.compute_kalman_states(y, x)
        z_scores = m30.compute_z_scores(errors)

        sig_beta_lb = pd.Series(betas).rolling(500, min_periods=2).mean().shift(1).fillna(betas[0]).to_numpy()
        hedge_beta_lb = pd.Series(ret_betas).rolling(500, min_periods=2).mean().shift(1).fillna(ret_betas[0]).to_numpy()
        mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
        mismatch = np.clip(mismatch, -10.0, 10.0)

        # Pair stability diagnostics
        corr_500 = pd.Series(x).rolling(500, min_periods=500).corr(pd.Series(y)).shift(1)
        corr_mean = float(corr_500.mean(skipna=True)) if corr_500.notna().any() else 0.0
        beta_std = float(np.std(betas))
        ret_beta_std = float(np.std(ret_betas))

        per_variant = defaultdict(list)
        per_exposure = defaultdict(list)

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

            if abs(z) >= THRESH_MOM and i - last_entry_mom >= MIN_GAP:
                direction = 1 if z > 0 else -1
                path = _trade_path(i, direction, "MOM", y, x, z_scores, ret_betas, betas, mismatch, active_leg)
                _consume_trade(per_variant, per_exposure, "MOM", active_leg, direction, path)
                last_entry_mom = i

            if abs(z) >= THRESH_REV and i - last_entry_rev >= MIN_GAP:
                direction = -1 if z > 0 else 1
                path = _trade_path(i, direction, "REV", y, x, z_scores, ret_betas, betas, mismatch, active_leg)
                _consume_trade(per_variant, per_exposure, "REV", active_leg, direction, path)
                last_entry_rev = i

        # Emit per pair metrics
        for strat in ["MOM", "REV"]:
            for variant in VARIANTS:
                key = (strat, variant["name"])
                pnl = np.asarray(per_variant[key], dtype=float)
                exposures = per_exposure[key]
                stats = _calc_metrics(pnl, exposures)
                rows.append(
                    {
                        "pair": name,
                        "strategy_type": strat,
                        "variant": variant["name"],
                        "corr_500_mean": corr_mean,
                        "beta_std": beta_std,
                        "ret_beta_std": ret_beta_std,
                        **stats,
                    }
                )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m30_hedge_pair_summary.csv"), index=False)
    print("Saved: data/analysis/m30_hedge_pair_summary.csv")


def _consume_trade(per_variant, per_exposure, strat, active_leg, direction, path):
    d_active = path["d_active"]
    d_other = path["d_other"]
    betas_ret = path["betas_ret"]
    betas_lvl = path["betas_lvl"]
    mismatch = path["mismatch"]

    for variant in VARIANTS:
        name = variant["name"]
        beta_kind = variant["beta_kind"]
        mm_min = variant["mm_min"]
        mm_max = variant["mm_max"]

        if beta_kind is None:
            pnl = direction * d_active * 10000.0
        else:
            betas = betas_ret if beta_kind == "return" else betas_lvl
            ratio = np.array([_hedge_ratio(active_leg, b) for b in betas], dtype=float)
            if mm_min is not None and mm_max is not None:
                mask = (np.abs(mismatch) >= mm_min) & (np.abs(mismatch) <= mm_max)
                ratio = np.where(mask, ratio, 0.0)
            pnl = direction * (d_active - ratio * d_other) * 10000.0

        per_variant[(strat, name)].append(float(np.sum(pnl)))
        per_exposure[(strat, name)].extend(np.abs(pnl).tolist())


if __name__ == "__main__":
    main()
