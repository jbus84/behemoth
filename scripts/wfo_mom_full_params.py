#!/usr/bin/env python3
"""
Walk-forward optimization (WFO) for full MOM strategy parameters (M15).

Sweeps:
- Z entry threshold
- Z stop level
- Z lookback window
- Loss-streak guardrail params (time-based cooldown)

Outputs:
- data/analysis/m15_mom_full_wfo_grid.csv
- data/analysis/m15_mom_full_wfo_best_folds.csv
- data/analysis/m15_mom_full_wfo_param_summary.csv
- data/analysis/m15_mom_best_param_trades_guardrail.csv
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

Z_ENTRIES = [1.5, 2.0, 2.5]
Z_STOPS = [3.0, 3.5, 4.0]
Z_LOOKBACKS = [250, 500, 750]

LOSS_STREAKS = [3, 4, 5]
COOLDOWN_DAYS = [7, 14, 21]

MIN_GAP = 20
MAX_HOLD = 500

WFO_WINDOWS = [
    (2018, 2021, 2022),
    (2019, 2022, 2023),
    (2020, 2023, 2024),
    (2021, 2024, 2025),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(trades: list[tuple[int, float]]) -> dict:
    if not trades:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
    df = pd.DataFrame(trades, columns=["exit_ts", "pnl"]).sort_values("exit_ts")
    pnl = df["pnl"].to_numpy()
    ts = df["exit_ts"].to_numpy()
    return dict(
        trades=int(len(pnl)),
        mean_pnl=float(np.mean(pnl)),
        total_pnl=float(np.sum(pnl)),
        max_dd=_max_dd(pnl),
        sharpe=sharpe_daily(pnl, ts),
        sharpe_active=sharpe_daily_active(pnl, ts),
        sharpe_trade=sharpe_trade(pnl, ts),
    )


def _exit_hit(direction: int, z: float, stop: float) -> bool:
    if direction == 1:
        return z < 0 or z > stop
    return z > 0 or z < -stop


def _build_pair_states():
    pair_states = []
    for name, fx, fy, cx, cy, _, _ in m15.PAIRS:
        df = m15.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        betas, errors, _ = m15.compute_kalman_states(y, x)
        z_map = {lb: m15.compute_z_scores(errors, window=lb) for lb in Z_LOOKBACKS}
        pair_states.append({"name": name, "y": y, "x": x, "ts": ts, "betas": betas, "z_map": z_map})
    return pair_states


def _build_trades(pair_states, z_entry: float, z_stop: float, z_lookback: int) -> list[dict]:
    trades = []
    for st in pair_states:
        name = st["name"]
        y = st["y"]
        x = st["x"]
        ts = st["ts"]
        betas = st["betas"]
        z_scores = st["z_map"][z_lookback]

        last_entry = -10_000
        start_idx = max(z_lookback, 500)
        for i in range(start_idx, len(y) - 2):
            z = z_scores[i]
            if abs(z) < z_entry or i - last_entry < MIN_GAP:
                continue

            beta = betas[i]
            if beta < 0.98:
                active_leg = "Y"
            elif beta > 1.02:
                active_leg = "X"
            else:
                continue

            direction = 1 if z > 0 else -1
            active = y if active_leg == "Y" else x
            entry_price = active[i]
            entry_ts = int(ts[i])

            exit_idx = min(i + MAX_HOLD, len(z_scores) - 1)
            for j in range(i + 1, exit_idx + 1):
                if _exit_hit(direction, z_scores[j], z_stop):
                    exit_idx = j
                    break

            pnl = float(direction * (active[exit_idx] - entry_price) * 10000.0)
            exit_ts = int(ts[exit_idx])
            year = int(pd.to_datetime(exit_ts, unit="ns", utc=True).year)
            trades.append({"pair": name, "entry_ts": entry_ts, "exit_ts": exit_ts, "pnl": pnl, "year": year})
            last_entry = i

    trades.sort(key=lambda r: r["exit_ts"])
    return trades


def _apply_loss_streak(trades, threshold, cooldown_days, train_years, test_years):
    kept_train = []
    kept_test = []
    state = {}

    for tr in trades:
        pair = tr["pair"]
        ts = tr["exit_ts"]
        pnl = tr["pnl"]
        year = tr["year"]

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        if year in train_years:
            kept_train.append((ts, pnl))
        elif year in test_years:
            kept_test.append((ts, pnl))

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= threshold:
                st["pause_until"] = ts + int(pd.Timedelta(days=cooldown_days).value)
                st["loss_streak"] = 0

    return kept_train, kept_test


def _apply_loss_streak_keep(trades, threshold, cooldown_days):
    kept = []
    state = {}
    for tr in trades:
        pair = tr["pair"]
        ts = tr["exit_ts"]
        pnl = tr["pnl"]
        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}
        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue
        kept.append(tr)
        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= threshold:
                st["pause_until"] = ts + int(pd.Timedelta(days=cooldown_days).value)
                st["loss_streak"] = 0
    return kept


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pair_states = _build_pair_states()
    print(f"Loaded pair states: {len(pair_states)}")

    # build trades for each base param set
    trade_cache = {}
    base_params = []
    for z_entry in Z_ENTRIES:
        for z_stop in Z_STOPS:
            for z_lb in Z_LOOKBACKS:
                key = (z_entry, z_stop, z_lb)
                trades = _build_trades(pair_states, z_entry, z_stop, z_lb)
                trade_cache[key] = trades
                base_params.append(key)
                print(f"Params {key}: trades={len(trades)}")

    grid_rows = []
    best_rows = []

    for start, end, test_year in WFO_WINDOWS:
        train_years = set(range(start, end + 1))
        test_years = {test_year}

        best = None
        best_params = None
        best_test = None

        for (z_entry, z_stop, z_lb) in base_params:
            trades = trade_cache[(z_entry, z_stop, z_lb)]
            for loss_streak in LOSS_STREAKS:
                for cooldown_days in COOLDOWN_DAYS:
                    train_trades, test_trades = _apply_loss_streak(
                        trades, loss_streak, cooldown_days, train_years, test_years
                    )
                    train_stats = _metrics(train_trades)
                    test_stats = _metrics(test_trades)

                    row = {
                        "train_years": f"{start}-{end}",
                        "test_year": test_year,
                        "z_entry": z_entry,
                        "z_stop": z_stop,
                        "z_lookback": z_lb,
                        "loss_streak": loss_streak,
                        "cooldown_days": cooldown_days,
                        **{f"train_{k}": v for k, v in train_stats.items()},
                        **{f"test_{k}": v for k, v in test_stats.items()},
                    }
                    grid_rows.append(row)

                    if best is None or train_stats["sharpe_trade"] > best:
                        best = train_stats["sharpe_trade"]
                        best_params = (z_entry, z_stop, z_lb, loss_streak, cooldown_days)
                        best_test = test_stats

        best_rows.append({
            "train_years": f"{start}-{end}",
            "test_year": test_year,
            "z_entry": best_params[0],
            "z_stop": best_params[1],
            "z_lookback": best_params[2],
            "loss_streak": best_params[3],
            "cooldown_days": best_params[4],
            **{f"test_{k}": v for k, v in best_test.items()},
        })

    grid_df = pd.DataFrame(grid_rows)
    grid_path = os.path.join(OUT_DIR, "m15_mom_full_wfo_grid.csv")
    grid_df.to_csv(grid_path, index=False)

    best_df = pd.DataFrame(best_rows)
    best_path = os.path.join(OUT_DIR, "m15_mom_full_wfo_best_folds.csv")
    best_df.to_csv(best_path, index=False)

    # summary across folds
    group_cols = ["z_entry", "z_stop", "z_lookback", "loss_streak", "cooldown_days"]
    summary = grid_df.groupby(group_cols).agg(
        test_sharpe_trade_mean=("test_sharpe_trade", "mean"),
        test_sharpe_trade_median=("test_sharpe_trade", "median"),
        test_mean_pnl_mean=("test_mean_pnl", "mean"),
        test_trades_mean=("test_trades", "mean"),
    ).reset_index().sort_values("test_sharpe_trade_mean", ascending=False)

    summary_path = os.path.join(OUT_DIR, "m15_mom_full_wfo_param_summary.csv")
    summary.to_csv(summary_path, index=False)

    # build and save guardrailed trades for best average params
    if not summary.empty:
        top = summary.iloc[0]
        key = (top["z_entry"], top["z_stop"], top["z_lookback"])
        trades = trade_cache[key]
        guardrailed = _apply_loss_streak_keep(
            trades, int(top["loss_streak"]), int(top["cooldown_days"])
        )
        out_trades = pd.DataFrame(guardrailed)
        out_trades.to_csv(os.path.join(OUT_DIR, "m15_mom_best_param_trades_guardrail.csv"), index=False)

    print(f"Saved: {grid_path}")
    print(f"Saved: {best_path}")
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
