#!/usr/bin/env python3
"""
Stress tests:
1) Remove 2020 entirely
2) Year bootstrap (200 samples)
Outputs:
- data/analysis/m5_stress_tests.csv
- data/analysis/m15_stress_tests.csv
- data/analysis/m5_bootstrap_summary.csv
- data/analysis/m15_bootstrap_summary.csv
"""

from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 14
BOOTSTRAP_N = 200

CONFIGS = [
    ("m5", "data/events/events_m5_8yr_v3_mom.csv", 5),
    ("m15", "data/events/events_m15_8yr_v3_mom.csv", 15),
]


def _max_dd(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    curve = np.cumsum(pnls)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0)
    pnl = df["pnl_bps"].to_numpy()
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


def _apply_guardrail(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("exit_ts").copy()
    keep = []
    state = {}
    cooldown_ns = int(pd.Timedelta(days=COOLDOWN_DAYS).value)

    for row in df.itertuples(index=False):
        pair = row.pair
        ts = int(row.exit_ts)
        pnl = float(row.pnl_bps)

        if pair not in state:
            state[pair] = {"loss_streak": 0, "pause_until": None}

        st = state[pair]
        if st["pause_until"] is not None and ts < st["pause_until"]:
            continue

        keep.append(row)

        if pnl > 0:
            st["loss_streak"] = 0
        else:
            st["loss_streak"] += 1
            if st["loss_streak"] >= LOSS_STREAK:
                st["pause_until"] = ts + cooldown_ns
                st["loss_streak"] = 0

    if not keep:
        return df.iloc[:0]
    return pd.DataFrame(keep)


def _bootstrap_years(df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    blocks = {y: df[df["year"] == y].copy() for y in years}
    samples = []
    offset = 0
    for y in np.random.choice(years, size=len(years), replace=True):
        block = blocks[y]
        if block.empty:
            continue
        block = block.copy()
        block["exit_ts"] = block["exit_ts"] + offset
        samples.append(block)
        # advance offset by ~400 days to avoid overlap
        offset += int(pd.Timedelta(days=400).value)
    if not samples:
        return df.iloc[:0]
    return pd.concat(samples, ignore_index=True)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        df["year"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce").dt.year
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)

        rows = []
        rows.append({"variant": "baseline", "guardrail": False, **_metrics(df)})
        rows.append({"variant": "baseline", "guardrail": True, **_metrics(_apply_guardrail(df))})

        # remove 2020
        df_no2020 = df[df["year"] != 2020].copy()
        rows.append({"variant": "no_2020", "guardrail": False, **_metrics(df_no2020)})
        rows.append({"variant": "no_2020", "guardrail": True, **_metrics(_apply_guardrail(df_no2020))})

        out = pd.DataFrame(rows)
        out.to_csv(os.path.join(OUT_DIR, f"{label}_stress_tests.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_stress_tests.csv")

        # bootstrap
        years = sorted(df["year"].dropna().unique())
        boot_rows = []
        for _ in range(BOOTSTRAP_N):
            sample = _bootstrap_years(df, years)
            m = _metrics(sample)
            g = _metrics(_apply_guardrail(sample))
            boot_rows.append({"guardrail": False, **m})
            boot_rows.append({"guardrail": True, **g})

        boot = pd.DataFrame(boot_rows)
        summary = boot.groupby("guardrail").agg(
            mean_pnl_p5=("mean_pnl", lambda s: s.quantile(0.05)),
            mean_pnl_p50=("mean_pnl", "median"),
            mean_pnl_p95=("mean_pnl", lambda s: s.quantile(0.95)),
            max_dd_p5=("max_dd", lambda s: s.quantile(0.05)),
            max_dd_p50=("max_dd", "median"),
            max_dd_p95=("max_dd", lambda s: s.quantile(0.95)),
        ).reset_index()
        summary.to_csv(os.path.join(OUT_DIR, f"{label}_bootstrap_summary.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_bootstrap_summary.csv")


if __name__ == "__main__":
    main()
