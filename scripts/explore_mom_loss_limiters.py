#!/usr/bin/env python3
"""
Explore per-symbol loss limiters for MOM trades (M15).

Limiter types:
- loss_rate: rolling loss rate >= threshold
- loss_streak: consecutive losses >= threshold
- rolling_pnl: rolling sum PnL <= threshold (bps)

Cooldowns:
- trade_count: skip next N trades
- time_days: skip trades until timestamp + N days

Outputs:
- data/analysis/mom_loss_limiter_sweep.csv
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

WINDOWS = [10, 20, 30]
COOLDOWNS = [
    ("trade_count", 20),
    ("trade_count", 50),
    ("time_days", 14),
]
LOSS_RATE_THRESH = 0.60
LOSS_STREAK_THRESH = 5
ROLLING_PNL_THRESHOLDS = [-100, -200, -300]


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
            trades.append(
                {
                    "pair": name,
                    "exit_ts": int(ts[exit_idx]),
                    "pnl": pnl,
                }
            )
            last_entry = i

    trades.sort(key=lambda r: r["exit_ts"])
    return trades


def _apply_limiter(trades, window, limiter_type, threshold, cooldown_type, cooldown_val):
    kept = []
    state = {}

    for tr in trades:
        pair = tr["pair"]
        ts = tr["exit_ts"]
        pnl = tr["pnl"]

        if pair not in state:
            state[pair] = {
                "history": deque(maxlen=window),
                "loss_streak": 0,
                "cooldown_remaining": 0,
                "pause_until": None,
            }

        st = state[pair]

        # cooldown checks
        if cooldown_type == "trade_count" and st["cooldown_remaining"] > 0:
            st["cooldown_remaining"] -= 1
            continue
        if cooldown_type == "time_days" and st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        # take trade
        kept.append((ts, pnl))

        # update history and streak
        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
        st["history"].append(pnl)

        # evaluate trigger only when we have full window (except for streak)
        trigger = False
        if limiter_type == "loss_rate":
            if len(st["history"]) >= window:
                losses = sum(1 for v in st["history"] if v <= 0)
                if losses / len(st["history"]) >= threshold:
                    trigger = True
        elif limiter_type == "loss_streak":
            if st["loss_streak"] >= threshold:
                trigger = True
        elif limiter_type == "rolling_pnl":
            if len(st["history"]) >= window:
                if sum(st["history"]) <= threshold:
                    trigger = True
        else:
            raise ValueError(f"Unknown limiter_type {limiter_type}")

        if trigger:
            if cooldown_type == "trade_count":
                st["cooldown_remaining"] = cooldown_val
            else:
                st["pause_until"] = ts + int(pd.Timedelta(days=cooldown_val).value)
            st["history"].clear()
            st["loss_streak"] = 0

    return kept


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    trades = _build_trades()
    print(f"Built MOM trades: {len(trades)}")

    rows = []
    for window in WINDOWS:
        for cooldown_type, cooldown_val in COOLDOWNS:
            # loss rate
            kept = _apply_limiter(
                trades,
                window=window,
                limiter_type="loss_rate",
                threshold=LOSS_RATE_THRESH,
                cooldown_type=cooldown_type,
                cooldown_val=cooldown_val,
            )
            stats = _metrics(kept)
            rows.append(
                {
                    "limiter": "loss_rate",
                    "window": window,
                    "threshold": LOSS_RATE_THRESH,
                    "cooldown_type": cooldown_type,
                    "cooldown_val": cooldown_val,
                    **stats,
                }
            )

            # loss streak
            kept = _apply_limiter(
                trades,
                window=window,
                limiter_type="loss_streak",
                threshold=LOSS_STREAK_THRESH,
                cooldown_type=cooldown_type,
                cooldown_val=cooldown_val,
            )
            stats = _metrics(kept)
            rows.append(
                {
                    "limiter": "loss_streak",
                    "window": window,
                    "threshold": LOSS_STREAK_THRESH,
                    "cooldown_type": cooldown_type,
                    "cooldown_val": cooldown_val,
                    **stats,
                }
            )

            # rolling pnl
            for thr in ROLLING_PNL_THRESHOLDS:
                kept = _apply_limiter(
                    trades,
                    window=window,
                    limiter_type="rolling_pnl",
                    threshold=thr,
                    cooldown_type=cooldown_type,
                    cooldown_val=cooldown_val,
                )
                stats = _metrics(kept)
                rows.append(
                    {
                        "limiter": "rolling_pnl",
                        "window": window,
                        "threshold": thr,
                        "cooldown_type": cooldown_type,
                        "cooldown_val": cooldown_val,
                        **stats,
                    }
                )

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT_DIR, "mom_loss_limiter_sweep.csv"), index=False)
    print("Saved: data/analysis/mom_loss_limiter_sweep.csv")


if __name__ == "__main__":
    main()
