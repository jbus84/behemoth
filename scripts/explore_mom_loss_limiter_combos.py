#!/usr/bin/env python3
"""
Explore MOM loss-streak limiters combined with regime gating and pair culling.

Outputs:
- data/analysis/mom_loss_limiter_combos.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
import build_meta_dataset_v3 as m15
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"

THRESH_MOM = 1.5
STOP_LEVEL = 3.5
MIN_GAP = 20
MAX_HOLD = 500

LOSS_STREAKS = [3, 4, 5, 6, 7]
COOLDOWNS = [
    ("time_days", 7),
    ("time_days", 14),
    ("time_days", 21),
    ("time_days", 30),
    ("trade_count", 20),
    ("trade_count", 50),
]

REGIME_CONFIGS = [
    {"name": "none", "corr_min": None, "mm_min": None, "mm_max": None, "bs_q": None},
    {"name": "corr0.3_mm0.7_1.5_bs50", "corr_min": 0.3, "mm_min": 0.7, "mm_max": 1.5, "bs_q": 0.5},
    {"name": "corr0.5_mm0.7_1.5_bs50", "corr_min": 0.5, "mm_min": 0.7, "mm_max": 1.5, "bs_q": 0.5},
    {"name": "corr0.3_mm0.8_1.2_bs30", "corr_min": 0.3, "mm_min": 0.8, "mm_max": 1.2, "bs_q": 0.3},
    {"name": "corr0.5_mm0.8_1.2_bs30", "corr_min": 0.5, "mm_min": 0.8, "mm_max": 1.2, "bs_q": 0.3},
]

CULL_SIZES = [0, 3, 5, 7]


def _exit_hit(direction: int, z: float) -> bool:
    if direction == 1:
        return z < 0 or z > STOP_LEVEL
    return z > 0 or z < -STOP_LEVEL


def _trade_path(entry_idx, direction, y, x, z_scores, active_leg):
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


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(trades: list[tuple[int, float]]) -> dict:
    if not trades:
        return dict(
            trades=0,
            win_rate=0.0,
            mean_pnl=0.0,
            total_pnl=0.0,
            max_dd=0.0,
            sharpe=0.0,
            sharpe_active=0.0,
            sharpe_trade=0.0,
        )
    df = pd.DataFrame(trades, columns=["ts", "pnl"]).sort_values("ts")
    pnl = df["pnl"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        win_rate=float((pnl > 0).mean() * 100.0),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, df["ts"].to_numpy()),
        sharpe_active=sharpe_daily_active(pnl, df["ts"].to_numpy()),
        sharpe_trade=sharpe_trade(pnl, df["ts"].to_numpy()),
    )


def _apply_loss_streak(trades, threshold, cooldown_type, cooldown_val):
    kept = []
    state = {}
    for tr in trades:
        pair = tr["pair"]
        ts = tr["exit_ts"]
        pnl = tr["pnl"]

        if pair not in state:
            state[pair] = {"loss_streak": 0, "cooldown_remaining": 0, "pause_until": None}

        st = state[pair]
        if cooldown_type == "trade_count" and st["cooldown_remaining"] > 0:
            st["cooldown_remaining"] -= 1
            continue
        if cooldown_type == "time_days" and st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        kept.append((ts, pnl))

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= threshold:
                if cooldown_type == "trade_count":
                    st["cooldown_remaining"] = cooldown_val
                else:
                    st["pause_until"] = ts + int(pd.Timedelta(days=cooldown_val).value)
                st["loss_streak"] = 0

    return kept


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    pair_states = {}
    trade_rows = []
    pair_pnls = defaultdict(list)

    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

        corr_500 = pd.Series(x).rolling(500, min_periods=500).corr(pd.Series(y)).shift(1).fillna(0.0).to_numpy()
        beta_stability = pd.Series(betas).rolling(100, min_periods=2).std().shift(1).fillna(0.0).to_numpy()
        sig_beta_lb = pd.Series(betas).rolling(500, min_periods=2).mean().shift(1).fillna(betas[0]).to_numpy()
        ret_betas = m15.compute_kalman_states(y, x)[2]
        hedge_beta_lb = pd.Series(ret_betas).rolling(500, min_periods=2).mean().shift(1).fillna(ret_betas[0]).to_numpy()
        mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
        mismatch = np.clip(mismatch, -10.0, 10.0)

        pair_states[name] = dict(
            corr_500=corr_500,
            beta_stability=beta_stability,
            mismatch=mismatch,
        )

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

            if abs(z) < THRESH_MOM or i - last_entry < MIN_GAP:
                continue

            direction = 1 if z > 0 else -1
            d_active, exit_idx = _trade_path(i, direction, y, x, z_scores, active_leg)
            pnl = float(np.sum(direction * d_active * 10000.0))
            exit_ts = int(ts[exit_idx])

            trade_rows.append(
                {
                    "pair": name,
                    "exit_ts": exit_ts,
                    "pnl": pnl,
                    "corr_500": float(corr_500[i]),
                    "beta_stability": float(beta_stability[i]),
                    "mismatch": float(mismatch[i]),
                }
            )
            pair_pnls[name].append(pnl)
            last_entry = i

    trade_rows.sort(key=lambda r: r["exit_ts"])
    trades = trade_rows

    # pair DD for culling
    pair_dd = {pair: _max_dd(np.asarray(pnls, dtype=float)) for pair, pnls in pair_pnls.items()}

    rows = []
    for cull_n in CULL_SIZES:
        dd_sorted = sorted(pair_dd.items(), key=lambda x: x[1])
        cull_set = set(pair for pair, _ in dd_sorted[:cull_n])

        for regime in REGIME_CONFIGS:
            # per-pair beta_stability thresholds
            bs_thresh = {}
            if regime["bs_q"] is not None:
                for pair in pair_pnls:
                    vals = [t["beta_stability"] for t in trades if t["pair"] == pair]
                    if vals:
                        bs_thresh[pair] = float(np.quantile(vals, regime["bs_q"]))

            gated = []
            for tr in trades:
                if tr["pair"] in cull_set:
                    continue
                if regime["corr_min"] is not None and abs(tr["corr_500"]) < regime["corr_min"]:
                    continue
                if regime["mm_min"] is not None:
                    mm = abs(tr["mismatch"])
                    if mm < regime["mm_min"] or mm > regime["mm_max"]:
                        continue
                if regime["bs_q"] is not None:
                    if tr["beta_stability"] > bs_thresh.get(tr["pair"], float("inf")):
                        continue
                gated.append(tr)

            # baseline for this gate
            base_stats = _metrics([(t["exit_ts"], t["pnl"]) for t in gated])
            rows.append(
                {
                    "cull_top_n": cull_n,
                    "regime": regime["name"],
                    "limiter": "baseline",
                    "threshold": None,
                    "cooldown_type": None,
                    "cooldown_val": None,
                    **base_stats,
                }
            )

            for streak in LOSS_STREAKS:
                for cooldown_type, cooldown_val in COOLDOWNS:
                    kept = _apply_loss_streak(gated, streak, cooldown_type, cooldown_val)
                    stats = _metrics(kept)
                    rows.append(
                        {
                            "cull_top_n": cull_n,
                            "regime": regime["name"],
                            "limiter": "loss_streak",
                            "threshold": streak,
                            "cooldown_type": cooldown_type,
                            "cooldown_val": cooldown_val,
                            **stats,
                        }
                    )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "mom_loss_limiter_combos.csv"), index=False)
    print("Saved: data/analysis/mom_loss_limiter_combos.csv")


if __name__ == "__main__":
    main()
