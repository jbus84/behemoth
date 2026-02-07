#!/usr/bin/env python3
"""
Walk-forward optimization (WFO) for MOM loss-streak limiter.

Selection metric: sharpe_trade on training.
Evaluation: apply selected params to test segment (warm-start state).

Outputs:
- data/analysis/mom_loss_limiter_wfo.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

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

WFO_WINDOWS = [
    (2018, 2021, 2022),
    (2019, 2022, 2023),
    (2020, 2023, 2024),
    (2021, 2024, 2025),
]


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
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
    df = pd.DataFrame(trades, columns=["ts", "pnl"]).sort_values("ts")
    pnl = df["pnl"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, df["ts"].to_numpy()),
        sharpe_active=sharpe_daily_active(pnl, df["ts"].to_numpy()),
        sharpe_trade=sharpe_trade(pnl, df["ts"].to_numpy()),
    )


def _build_trades() -> list[dict]:
    trades = []
    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_scores = m15.compute_z_scores(errors)

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
            year = int(pd.to_datetime(exit_ts, unit="ns", utc=True).year)
            trades.append({"pair": name, "exit_ts": exit_ts, "pnl": pnl, "year": year})
            last_entry = i

    trades.sort(key=lambda r: r["exit_ts"])
    return trades


def _apply_loss_streak(trades, threshold, cooldown_type, cooldown_val, train_years, test_years):
    kept_train = []
    kept_test = []
    state = {}

    for tr in trades:
        pair = tr["pair"]
        ts = tr["exit_ts"]
        pnl = tr["pnl"]
        year = tr["year"]

        if pair not in state:
            state[pair] = {"loss_streak": 0, "cooldown_remaining": 0, "pause_until": None}

        st = state[pair]
        if cooldown_type == "trade_count" and st["cooldown_remaining"] > 0:
            st["cooldown_remaining"] -= 1
            continue
        if cooldown_type == "time_days" and st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        # take trade
        if year in train_years:
            kept_train.append((ts, pnl))
        elif year in test_years:
            kept_test.append((ts, pnl))

        # update streak
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

    return kept_train, kept_test


def _baseline(trades, train_years, test_years):
    train = [(t["exit_ts"], t["pnl"]) for t in trades if t["year"] in train_years]
    test = [(t["exit_ts"], t["pnl"]) for t in trades if t["year"] in test_years]
    return _metrics(train), _metrics(test)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    trades = _build_trades()
    print(f"Built MOM trades: {len(trades)}")

    rows = []
    for start, end, test_year in WFO_WINDOWS:
        train_years = set(range(start, end + 1))
        test_years = {test_year}

        base_train, base_test = _baseline(trades, train_years, test_years)

        best = None
        best_params = None
        best_test = None

        for streak in LOSS_STREAKS:
            for cooldown_type, cooldown_val in COOLDOWNS:
                train_trades, test_trades = _apply_loss_streak(
                    trades, streak, cooldown_type, cooldown_val, train_years, test_years
                )
                train_stats = _metrics(train_trades)
                test_stats = _metrics(test_trades)

                score = train_stats["sharpe_trade"]
                if best is None or score > best:
                    best = score
                    best_params = (streak, cooldown_type, cooldown_val)
                    best_test = test_stats

        rows.append(
            {
                "train_years": f"{start}-{end}",
                "test_year": test_year,
                "selection_metric": "sharpe_trade",
                "best_streak": best_params[0],
                "best_cooldown_type": best_params[1],
                "best_cooldown_val": best_params[2],
                "train_sharpe_trade": best,
                "test_trades": best_test["trades"],
                "test_mean_pnl": best_test["mean_pnl"],
                "test_total_pnl": best_test["total_pnl"],
                "test_max_dd": best_test["max_dd"],
                "test_sharpe": best_test["sharpe"],
                "test_sharpe_active": best_test["sharpe_active"],
                "test_sharpe_trade": best_test["sharpe_trade"],
                "baseline_test_trades": base_test["trades"],
                "baseline_test_mean_pnl": base_test["mean_pnl"],
                "baseline_test_total_pnl": base_test["total_pnl"],
                "baseline_test_max_dd": base_test["max_dd"],
                "baseline_test_sharpe": base_test["sharpe"],
                "baseline_test_sharpe_active": base_test["sharpe_active"],
                "baseline_test_sharpe_trade": base_test["sharpe_trade"],
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "mom_loss_limiter_wfo.csv"), index=False)
    print("Saved: data/analysis/mom_loss_limiter_wfo.csv")


if __name__ == "__main__":
    main()
