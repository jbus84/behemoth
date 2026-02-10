#!/usr/bin/env python3
"""
Analyze why the loss-streak guardrail is effective.

Outputs per timeframe (m5/m15):
- data/analysis/<bar>_guardrail_effectiveness_summary.csv
- data/analysis/<bar>_guardrail_streak_stats.csv
- data/analysis/<bar>_guardrail_streak_dist.csv
- data/analysis/<bar>_guardrail_skip_stats.csv
- data/analysis/<bar>_guardrail_symbol_pauses.csv
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "pipelines"))
sys.path.append(os.path.join(os.getcwd(), "scripts"))
from pipelines import build_events_m15 as m15
from pipelines import build_events_m5 as m5
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"

Z_ENTRY = 1.5
Z_STOP = 4.0
Z_LOOKBACK = 750
LOSS_STREAK = 3
COOLDOWN_DAYS = 7

MIN_GAP = 20
MAX_HOLD = 500


def _exit_hit(direction: int, z: float) -> bool:
    if direction == 1:
        return z < 0 or z > Z_STOP
    return z > 0 or z < -Z_STOP


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
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


def build_trades(mod) -> pd.DataFrame:
    trades = []
    for name, fx, fy, cx, cy, _, _ in mod.PAIRS:
        df = mod.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue
        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()
        betas, errors, _ = mod.compute_kalman_states(y, x)
        z_scores = mod.compute_z_scores(errors, window=Z_LOOKBACK)

        last_entry = -10_000
        start_idx = max(Z_LOOKBACK, 500)
        for i in range(start_idx, len(y) - 2):
            z = z_scores[i]
            if abs(z) < Z_ENTRY or i - last_entry < MIN_GAP:
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
                if _exit_hit(direction, z_scores[j]):
                    exit_idx = j
                    break

            pnl = float(direction * (active[exit_idx] - entry_price) * 10000.0)
            exit_ts = int(ts[exit_idx])
            year = int(pd.to_datetime(exit_ts, unit="ns", utc=True).year)
            trades.append({
                "pair": name,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "pnl": pnl,
                "year": year,
            })
            last_entry = i

    return pd.DataFrame(trades).sort_values("exit_ts")


def apply_guardrail(trades: pd.DataFrame):
    kept = []
    skipped = []
    pauses = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in trades.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
        pnl = float(row.pnl)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None, "pauses": 0}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            skipped.append(row)
            continue

        kept.append(row)

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0
                st["pauses"] += 1
                pauses.append({"pair": pair, "pause_start": ts, "pause_until": st["pause_until"]})

    kept_df = pd.DataFrame(kept)
    skipped_df = pd.DataFrame(skipped)
    pauses_df = pd.DataFrame(pauses)
    return kept_df, skipped_df, pauses_df


def streak_stats(trades: pd.DataFrame):
    # per-trade prev loss streak
    trades = trades.sort_values(["pair", "exit_ts"]).copy()
    trades["prev_loss_streak"] = 0

    for pair, sub in trades.groupby("pair"):
        streak = 0
        idxs = sub.index.to_numpy()
        for idx in idxs:
            trades.loc[idx, "prev_loss_streak"] = streak
            pnl = trades.loc[idx, "pnl"]
            if pnl > 0:
                streak = 0
            else:
                streak += 1

    # conditional next-trade stats by prev_loss_streak
    rows = []
    for k in range(1, 7):
        sub = trades[trades["prev_loss_streak"] == k]
        if sub.empty:
            rows.append({"prev_loss_streak": k, "count": 0, "mean_pnl": 0.0, "win_rate": 0.0})
            continue
        rows.append({
            "prev_loss_streak": k,
            "count": int(len(sub)),
            "mean_pnl": float(sub["pnl"].mean()),
            "win_rate": float((sub["pnl"] > 0).mean()),
        })

    # distribution of loss streak lengths
    dist_rows = []
    for pair, sub in trades.groupby("pair"):
        streak = 0
        for pnl in sub["pnl"].to_numpy():
            if pnl <= 0:
                streak += 1
            else:
                if streak > 0:
                    dist_rows.append({"pair": pair, "streak_len": streak})
                streak = 0
        if streak > 0:
            dist_rows.append({"pair": pair, "streak_len": streak})

    dist = pd.DataFrame(dist_rows)
    if dist.empty:
        dist_summary = pd.DataFrame(columns=["streak_len", "count"])
    else:
        dist_summary = dist.groupby("streak_len").size().reset_index(name="count")

    # loss concentration: losses with prev_loss_streak >= 2 (third loss and beyond)
    loss_trades = trades[trades["pnl"] <= 0]
    total_loss = float(loss_trades["pnl"].sum()) if not loss_trades.empty else 0.0
    tail_loss = float(loss_trades[loss_trades["prev_loss_streak"] >= 2]["pnl"].sum()) if not loss_trades.empty else 0.0
    loss_concentration = 0.0
    if total_loss != 0:
        loss_concentration = tail_loss / total_loss

    return pd.DataFrame(rows), dist_summary, loss_concentration


def skip_stats(skipped: pd.DataFrame):
    if skipped.empty:
        return pd.DataFrame([{
            "skipped_trades": 0,
            "skipped_mean_pnl": 0.0,
            "skipped_win_rate": 0.0,
            "skipped_total_pnl": 0.0,
        }])
    return pd.DataFrame([{
        "skipped_trades": int(len(skipped)),
        "skipped_mean_pnl": float(skipped["pnl"].mean()),
        "skipped_win_rate": float((skipped["pnl"] > 0).mean()),
        "skipped_total_pnl": float(skipped["pnl"].sum()),
    }])


def symbol_pause_stats(skipped: pd.DataFrame, pauses: pd.DataFrame):
    if skipped.empty:
        return pd.DataFrame(columns=["pair", "pauses", "skipped_trades", "skipped_mean_pnl", "skipped_total_pnl"])
    skipped_stats = skipped.groupby("pair").agg(
        skipped_trades=("pnl", "size"),
        skipped_mean_pnl=("pnl", "mean"),
        skipped_total_pnl=("pnl", "sum"),
    ).reset_index()
    pause_counts = pauses.groupby("pair").size().reset_index(name="pauses") if not pauses.empty else pd.DataFrame(columns=["pair", "pauses"])
    out = skipped_stats.merge(pause_counts, on="pair", how="left").fillna({"pauses": 0})
    out["pauses"] = out["pauses"].astype(int)
    return out


def run(mod, label: str):
    os.makedirs(OUT_DIR, exist_ok=True)
    trades = build_trades(mod)
    baseline = _metrics(trades)

    kept, skipped, pauses = apply_guardrail(trades)
    guardrail = _metrics(kept)

    streak_df, dist_df, loss_conc = streak_stats(trades)
    skip_df = skip_stats(skipped)
    symbol_df = symbol_pause_stats(skipped, pauses)

    summary = pd.DataFrame([{
        "label": label,
        "z_entry": Z_ENTRY,
        "z_stop": Z_STOP,
        "z_lookback": Z_LOOKBACK,
        "loss_streak": LOSS_STREAK,
        "cooldown_days": COOLDOWN_DAYS,
        "baseline_trades": baseline["trades"],
        "baseline_mean_pnl": baseline["mean_pnl"],
        "baseline_total_pnl": baseline["total_pnl"],
        "baseline_max_dd": baseline["max_dd"],
        "baseline_sharpe": baseline["sharpe"],
        "guardrail_trades": guardrail["trades"],
        "guardrail_mean_pnl": guardrail["mean_pnl"],
        "guardrail_total_pnl": guardrail["total_pnl"],
        "guardrail_max_dd": guardrail["max_dd"],
        "guardrail_sharpe": guardrail["sharpe"],
        "skipped_trades": int(len(skipped)),
        "skipped_mean_pnl": float(skipped["pnl"].mean()) if not skipped.empty else 0.0,
        "skipped_win_rate": float((skipped["pnl"] > 0).mean()) if not skipped.empty else 0.0,
        "loss_concentration_ratio": loss_conc,
    }])

    summary.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_effectiveness_summary.csv"), index=False)
    streak_df.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_streak_stats.csv"), index=False)
    dist_df.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_streak_dist.csv"), index=False)
    skip_df.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_skip_stats.csv"), index=False)
    symbol_df.to_csv(os.path.join(OUT_DIR, f"{label}_guardrail_symbol_pauses.csv"), index=False)

    print(f"Saved guardrail effectiveness outputs for {label}")


def main() -> None:
    run(m5, "m5")
    run(m15, "m15")


if __name__ == "__main__":
    main()
