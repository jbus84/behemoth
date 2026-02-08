#!/usr/bin/env python3
"""
Robustness tests for MOM strategy (M5) using guardrailed trades.
Covers:
5) Universe drift
6) Parameter stability (from WFO grid)
7) Session robustness
8) Tail-risk concentration

Outputs:
- data/analysis/m5_universe_drift.csv
- data/analysis/m5_param_stability.csv
- data/analysis/m5_session_robustness.csv
- data/analysis/m5_tail_risk_concentration.csv
"""

from __future__ import annotations

import os
import random

import numpy as np
import pandas as pd

from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
TRADES_PATH = os.path.join(OUT_DIR, "m5_mom_best_param_trades_guardrail.csv")
WFO_SUMMARY_PATH = os.path.join(OUT_DIR, "m5_mom_full_wfo_param_summary.csv")

SESSIONS = [
    ("Asia", 0, 7),
    ("London", 7, 13),
    ("New_York", 13, 21),
    ("Late", 21, 24),
]


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


def _session_from_hour(h: int) -> str:
    for name, start, end in SESSIONS:
        if start <= h < end:
            return name
    return "Unknown"


def universe_drift(trades: pd.DataFrame) -> pd.DataFrame:
    pairs = sorted(trades["pair"].unique())
    rows = []
    rng = random.Random(7)
    for frac in [0.1, 0.2, 0.3, 0.4]:
        drop_n = max(1, int(round(len(pairs) * frac)))
        for seed in range(20):
            rng.seed(seed + int(frac * 1000))
            drop = set(rng.sample(pairs, drop_n))
            df = trades[~trades["pair"].isin(drop)]
            stats = _metrics(df)
            rows.append({
                "drop_frac": frac,
                "drop_n": drop_n,
                "seed": seed,
                **stats,
            })
    return pd.DataFrame(rows)


def param_stability() -> pd.DataFrame:
    if not os.path.exists(WFO_SUMMARY_PATH):
        return pd.DataFrame()
    df = pd.read_csv(WFO_SUMMARY_PATH)
    if df.empty:
        return df
    best = df.iloc[0]
    def dist(row):
        return (
            abs(row["z_entry"] - best["z_entry"]) / 0.5
            + abs(row["z_stop"] - best["z_stop"]) / 0.5
            + abs(row["z_lookback"] - best["z_lookback"]) / 250.0
            + abs(row["loss_streak"] - best["loss_streak"]) / 1.0
            + abs(row["cooldown_days"] - best["cooldown_days"]) / 7.0
        )
    df = df.copy()
    df["param_distance"] = df.apply(dist, axis=1)
    buckets = []
    for max_d in [0.0, 1.0, 2.0, 3.0]:
        sub = df[df["param_distance"] <= max_d]
        if sub.empty:
            buckets.append({"max_param_distance": max_d, "count": 0})
            continue
        buckets.append({
            "max_param_distance": max_d,
            "count": int(len(sub)),
            "test_sharpe_trade_mean": float(sub["test_sharpe_trade_mean"].mean()),
            "test_sharpe_trade_p25": float(sub["test_sharpe_trade_mean"].quantile(0.25)),
            "test_sharpe_trade_p50": float(sub["test_sharpe_trade_mean"].quantile(0.50)),
            "test_sharpe_trade_p75": float(sub["test_sharpe_trade_mean"].quantile(0.75)),
        })
    return pd.DataFrame(buckets)


def session_robustness(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    entry_dt = pd.to_datetime(df["entry_ts"], unit="ns", utc=True)
    df["hour"] = entry_dt.dt.hour
    df["session"] = df["hour"].map(_session_from_hour)
    rows = []
    for session, sub in df.groupby("session"):
        stats = _metrics(sub)
        rows.append({"session": session, **stats})
    return pd.DataFrame(rows).sort_values("session")


def tail_risk_concentration(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["month"] = pd.to_datetime(df["exit_ts"], unit="ns", utc=True).dt.to_period("M").astype(str)

    rows = []
    month_pnl = df.groupby("month")["pnl"].sum().sort_values()
    for n in [1, 2, 3, 6]:
        bad_months = set(month_pnl.head(n).index)
        sub = df[~df["month"].isin(bad_months)]
        stats = _metrics(sub)
        rows.append({"remove_type": "worst_months", "remove_n": n, **stats})

    pair_pnl = df.groupby("pair")["pnl"].sum().sort_values()
    for n in [1, 2, 3, 5]:
        bad_pairs = set(pair_pnl.head(n).index)
        sub = df[~df["pair"].isin(bad_pairs)]
        stats = _metrics(sub)
        rows.append({"remove_type": "worst_pairs", "remove_n": n, **stats})

    return pd.DataFrame(rows)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    if not os.path.exists(TRADES_PATH):
        raise SystemExit(f"Missing trades file: {TRADES_PATH}")

    trades = pd.read_csv(TRADES_PATH)

    drift = universe_drift(trades)
    drift.to_csv(os.path.join(OUT_DIR, "m5_universe_drift.csv"), index=False)

    stability = param_stability()
    stability.to_csv(os.path.join(OUT_DIR, "m5_param_stability.csv"), index=False)

    sessions = session_robustness(trades)
    sessions.to_csv(os.path.join(OUT_DIR, "m5_session_robustness.csv"), index=False)

    tail = tail_risk_concentration(trades)
    tail.to_csv(os.path.join(OUT_DIR, "m5_tail_risk_concentration.csv"), index=False)

    print("Saved robustness outputs to data/analysis")


if __name__ == "__main__":
    main()
