#!/usr/bin/env python3
"""
Bootstrap robustness tests:
1) Month bootstrap (sample months with replacement).
2) Trade-block bootstrap (sample contiguous blocks of N trades).

Outputs:
- data/analysis/m5_bootstrap_month_summary.csv
- data/analysis/m15_bootstrap_month_summary.csv
- data/analysis/m5_bootstrap_tradeblock_summary.csv
- data/analysis/m15_bootstrap_tradeblock_summary.csv
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "src"))
from behemoth.core.guardrail import apply_loss_streak_guardrail
from behemoth.core.metrics import sharpe_daily, sharpe_daily_active, sharpe_trade

OUT_DIR = "data/analysis"
LOSS_STREAK = 3
COOLDOWN_DAYS = 7
BOOTSTRAP_N = int(os.getenv("BOOTSTRAP_N", "200"))
BLOCK_SIZES = [int(x) for x in os.getenv("BLOCK_SIZES", "200,500").split(",") if x.strip()]

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
        return dict(trades=0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0, sharpe=0.0, sharpe_active=0.0, sharpe_trade=0.0)
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
    return apply_loss_streak_guardrail(
        df,
        loss_threshold=0.0,
        loss_streak=LOSS_STREAK,
        cooldown_days=COOLDOWN_DAYS,
    )


def _bootstrap_blocks(blocks: list[pd.DataFrame]) -> pd.DataFrame:
    if not blocks:
        return pd.DataFrame()
    spans = []
    for b in blocks:
        span = int(b["exit_ts"].max() - b["exit_ts"].min()) if not b.empty else 0
        spans.append(max(span, int(pd.Timedelta(days=1).value)))
    samples = []
    offset = 0
    for idx in np.random.randint(0, len(blocks), size=len(blocks)):
        block = blocks[idx]
        if block.empty:
            continue
        b = block.copy()
        b["exit_ts"] = b["exit_ts"] - int(b["exit_ts"].min()) + offset
        samples.append(b)
        offset += spans[idx] + int(pd.Timedelta(days=1).value)
    if not samples:
        return pd.DataFrame()
    return pd.concat(samples, ignore_index=True)


def _month_blocks(df: pd.DataFrame) -> list[pd.DataFrame]:
    return [g.copy() for _, g in df.groupby("year_month")]


def _trade_blocks(df: pd.DataFrame, block_size: int) -> list[pd.DataFrame]:
    df = df.sort_values("exit_ts").copy()
    blocks = []
    for start in range(0, len(df), block_size):
        block = df.iloc[start:start + block_size].copy()
        if not block.empty:
            blocks.append(block)
    return blocks


def _bootstrap_summary(samples: list[pd.DataFrame]) -> pd.DataFrame:
    boot_rows = []
    for sample in samples:
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
    return summary


def main() -> None:  # pragma: no cover
    os.makedirs(OUT_DIR, exist_ok=True)

    for label, path, bar_minutes in CONFIGS:
        df = pd.read_csv(path)
        df["timestamp"] = df["timestamp"].astype("int64")
        bar_ns = int(pd.Timedelta(minutes=bar_minutes).value)
        durations = df["duration_bars"].astype(int)
        timeout_adjust = (durations >= 500).astype(int)
        df["exit_ts"] = df["timestamp"] + ((durations - timeout_adjust) * bar_ns)
        dt = pd.to_datetime(df["timestamp"], unit="ns", utc=True, errors="coerce")
        df["year"] = dt.dt.year
        df["year_month"] = dt.dt.year * 100 + dt.dt.month

        # Month bootstrap
        month_blocks = _month_blocks(df)
        month_samples = [_bootstrap_blocks(month_blocks) for _ in range(BOOTSTRAP_N)]
        month_summary = _bootstrap_summary(month_samples)
        month_summary.to_csv(os.path.join(OUT_DIR, f"{label}_bootstrap_month_summary.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_bootstrap_month_summary.csv")

        # Trade-block bootstrap
        trade_rows = []
        for block_size in BLOCK_SIZES:
            blocks = _trade_blocks(df, block_size)
            samples = [_bootstrap_blocks(blocks) for _ in range(BOOTSTRAP_N)]
            summary = _bootstrap_summary(samples)
            summary["block_size"] = block_size
            trade_rows.append(summary)
        trade_out = pd.concat(trade_rows, ignore_index=True)
        trade_out.to_csv(os.path.join(OUT_DIR, f"{label}_bootstrap_tradeblock_summary.csv"), index=False)
        print(f"Saved: {OUT_DIR}/{label}_bootstrap_tradeblock_summary.csv")


if __name__ == "__main__":
    main()
