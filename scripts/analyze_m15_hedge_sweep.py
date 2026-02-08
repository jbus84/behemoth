#!/usr/bin/env python3
"""
Hedge DD-reduction sweep on 15m data.
Tests:
 - pair culling (top N DD contributors)
 - regime gating (corr, beta stability, beta mismatch band)
 - hedge modes (unhedged, ret_beta, level_beta, hybrid)

Outputs:
 - data/analysis/m15_hedge_sweep_summary.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15
from metrics import sharpe_daily

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
THRESH_REV = 2.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500
HEDGE_CLIP = 10.0


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
    active_leg: str,
) -> dict:
    active = y if active_leg == "Y" else x
    other = x if active_leg == "Y" else y

    d_active = []
    d_other = []
    betas_ret = []
    betas_lvl = []

    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    exit_idx = end

    for i in range(entry_idx + 1, end + 1):
        d_active.append(active[i] - active[i - 1])
        d_other.append(other[i] - other[i - 1])
        betas_ret.append(ret_betas[i])
        betas_lvl.append(level_betas[i])
        if _exit_hit(strategy_type, direction, z_scores[i]):
            exit_idx = i
            break

    return {
        "d_active": np.asarray(d_active),
        "d_other": np.asarray(d_other),
        "betas_ret": np.asarray(betas_ret),
        "betas_lvl": np.asarray(betas_lvl),
        "exit_idx": exit_idx,
    }


def _pnl_from_path(path: dict, direction: int, active_leg: str, hedge_mode: str, strategy_type: str) -> float:
    d_active = path["d_active"]
    d_other = path["d_other"]
    if hedge_mode == "unhedged":
        pnl = direction * d_active * 10000.0
        return float(np.sum(pnl))

    if hedge_mode == "ret_beta":
        betas = path["betas_ret"]
    elif hedge_mode == "level_beta":
        betas = path["betas_lvl"]
    elif hedge_mode == "hybrid":
        betas = path["betas_lvl"] if strategy_type == "MOM" else path["betas_ret"]
    else:
        raise ValueError(f"Unknown hedge mode {hedge_mode}")

    ratio = np.array([_hedge_ratio(active_leg, b) for b in betas], dtype=float)
    pnl = direction * (d_active - ratio * d_other) * 10000.0
    return float(np.sum(pnl))


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


def _pair_dd_unhedged(pair_trades: dict) -> dict:
    out = {}
    for pair, pnls in pair_trades.items():
        out[pair] = _max_dd(np.asarray(pnls, dtype=float))
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    # Collect pair data + precompute regime arrays
    pair_states = {}
    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        betas, errors, ret_betas = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

        # regime features
        corr_500 = pd.Series(x).rolling(500, min_periods=500).corr(pd.Series(y)).shift(1).fillna(0.0).to_numpy()
        beta_stability = pd.Series(betas).rolling(100, min_periods=2).std().shift(1).fillna(0.0).to_numpy()
        sig_beta_lb = pd.Series(betas).rolling(500, min_periods=2).mean().shift(1).fillna(betas[0]).to_numpy()
        hedge_beta_lb = pd.Series(ret_betas).rolling(500, min_periods=2).mean().shift(1).fillna(ret_betas[0]).to_numpy()
        mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
        mismatch = np.clip(mismatch, -10.0, 10.0)

        pair_states[name] = {
            "y": y,
            "x": x,
            "betas": betas,
            "ret_betas": ret_betas,
            "z_scores": z_scores,
            "corr_500": corr_500,
            "beta_stability": beta_stability,
            "mismatch": mismatch,
            "ts": df["timestamp"].to_numpy(),
        }

    # Precompute trades per pair/strategy once
    trade_book: dict[str, dict[str, list[dict]]] = {"MOM": {}, "REV": {}}
    pair_dd = {"MOM": {}, "REV": {}}

    for pair, state in pair_states.items():
        y = state["y"]
        x = state["x"]
        betas = state["betas"]
        ret_betas = state["ret_betas"]
        z_scores = state["z_scores"]
        corr_500 = state["corr_500"]
        beta_stability = state["beta_stability"]
        mismatch = state["mismatch"]

        for strat in ["MOM", "REV"]:
            trades = []
            pnls_unhedged = []
            last_entry = 0
            for i in range(500, len(y) - 2):
                z = z_scores[i]
                beta = betas[i]
                if beta < 0.98:
                    active_leg = "Y"
                elif beta > 1.02:
                    active_leg = "X"
                else:
                    continue

                if strat == "MOM":
                    if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                        continue
                    direction = 1 if z > 0 else -1
                else:
                    if abs(z) < THRESH_REV or i - last_entry < MIN_GAP:
                        continue
                    direction = -1 if z > 0 else 1

                path = _trade_path(i, direction, strat, y, x, z_scores, ret_betas, betas, active_leg)
                pnl_unhedged = _pnl_from_path(path, direction, active_leg, "unhedged", strat)
                pnl_ret = _pnl_from_path(path, direction, active_leg, "ret_beta", strat)
                pnl_lvl = _pnl_from_path(path, direction, active_leg, "level_beta", strat)
                pnl_hybrid = _pnl_from_path(path, direction, active_leg, "hybrid", strat)
                exit_ts = state["ts"][path["exit_idx"]]

                trades.append(
                    {
                        "corr_500": corr_500[i],
                        "beta_stability": beta_stability[i],
                        "mismatch": mismatch[i],
                        "pnl_unhedged": pnl_unhedged,
                        "pnl_ret_beta": pnl_ret,
                        "pnl_level_beta": pnl_lvl,
                        "pnl_hybrid": pnl_hybrid,
                        "exit_ts": exit_ts,
                    }
                )
                pnls_unhedged.append(pnl_unhedged)
                last_entry = i

            trade_book[strat][pair] = trades
            pair_dd[strat][pair] = _max_dd(np.asarray(pnls_unhedged, dtype=float)) if pnls_unhedged else 0.0

    # Regime gating configs
    regime_configs = [
        {"name": "none", "corr_min": None, "mm_min": None, "mm_max": None, "bs_q": None},
        {"name": "corr0.3_mm0.7_1.5_bs50", "corr_min": 0.3, "mm_min": 0.7, "mm_max": 1.5, "bs_q": 0.5},
        {"name": "corr0.5_mm0.7_1.5_bs50", "corr_min": 0.5, "mm_min": 0.7, "mm_max": 1.5, "bs_q": 0.5},
        {"name": "corr0.3_mm0.8_1.2_bs30", "corr_min": 0.3, "mm_min": 0.8, "mm_max": 1.2, "bs_q": 0.3},
        {"name": "corr0.5_mm0.8_1.2_bs30", "corr_min": 0.5, "mm_min": 0.8, "mm_max": 1.2, "bs_q": 0.3},
    ]

    cull_sizes = [0, 3, 5, 7]
    hedge_modes = ["unhedged", "ret_beta", "level_beta", "hybrid"]

    rows = []
    for strat in ["MOM", "REV"]:
        # Determine pair rankings for culling (most negative DD first)
        dd_sorted = sorted(pair_dd[strat].items(), key=lambda x: x[1])
        for cull_n in cull_sizes:
            cull_set = set(pair for pair, _ in dd_sorted[:cull_n])
            for regime in regime_configs:
                for hedge_mode in hedge_modes:
                    if hedge_mode == "hybrid" and strat == "REV":
                        # hybrid only differs for MOM vs REV, but keep for uniformity
                        pass
                    pnls = []
                    ts_list = []
                    for pair, trades in trade_book[strat].items():
                        if pair in cull_set:
                            continue
                        # beta stability threshold per pair
                        bs_thresh = None
                        if regime["bs_q"] is not None:
                            bs_vals = np.asarray([t["beta_stability"] for t in trades], dtype=float)
                            if len(bs_vals):
                                bs_thresh = np.quantile(bs_vals[np.isfinite(bs_vals)], regime["bs_q"])

                        for tr in trades:
                            # regime gating
                            if regime["corr_min"] is not None and abs(tr["corr_500"]) < regime["corr_min"]:
                                continue
                            if bs_thresh is not None and tr["beta_stability"] > bs_thresh:
                                continue
                            if regime["mm_min"] is not None:
                                mm = abs(tr["mismatch"])
                                if mm < regime["mm_min"] or mm > regime["mm_max"]:
                                    continue

                            if hedge_mode == "unhedged":
                                pnls.append(tr["pnl_unhedged"])
                            elif hedge_mode == "ret_beta":
                                pnls.append(tr["pnl_ret_beta"])
                            elif hedge_mode == "level_beta":
                                pnls.append(tr["pnl_level_beta"])
                            elif hedge_mode == "hybrid":
                                pnls.append(tr["pnl_hybrid"])
                            ts_list.append(tr["exit_ts"])

                    stats = _metrics(pnls, ts_list)
                    rows.append(
                        {
                            "strategy_type": strat,
                            "hedge_mode": hedge_mode,
                            "cull_top_n": cull_n,
                            "regime": regime["name"],
                            **stats,
                        }
                    )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "m15_hedge_sweep_summary.csv"), index=False)
    print("Saved: data/analysis/m15_hedge_sweep_summary.csv")


if __name__ == "__main__":
    main()
