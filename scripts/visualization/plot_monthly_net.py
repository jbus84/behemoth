#!/usr/bin/env python3
"""
Plot monthly net totals for M5/M15 using MOM-only thresholds.
Outputs: docs/figures/monthly_net_m5_m15.png
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def _load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["month"] = pd.to_datetime(df["month"], errors="coerce")
    return df.dropna(subset=["month"])


def _pick_net_col(df: pd.DataFrame) -> str:
    for col in ["net_total_pnl_bps", "net_total"]:
        if col in df.columns:
            return col
    raise ValueError("No net total column found in monthly data.")


def _prep(df: pd.DataFrame, edge: int | None = None) -> pd.DataFrame:
    if edge is not None and "edge_threshold" in df.columns:
        sub = df[df["edge_threshold"] == edge].copy()
    else:
        sub = df.copy()
    sub = sub.sort_values("month")
    net_col = _pick_net_col(df)
    mean_col = "net_mean_pnl_bps" if "net_mean_pnl_bps" in df.columns else "net_mean"
    return sub[["month", net_col, mean_col]].rename(
        columns={net_col: "net_total_pnl_bps", mean_col: "net_mean_pnl_bps"}
    )


def main() -> None:
    fig_dir = Path("docs/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)

    m5 = _load("data/analysis/m5_two_stage_monthly_mom_only.csv")
    m15 = _load("data/analysis/m15_two_stage_monthly_mom_only.csv")

    fig, axes = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)

    # Split thresholds are selected on train; plot single series per timeframe.
    m5_sub = _prep(m5, edge=None)
    m15_sub = _prep(m15, edge=None)
    axes[0].plot(m5_sub["month"], m5_sub["net_total_pnl_bps"], label="M5", color="#2563eb")
    axes[0].plot(m15_sub["month"], m15_sub["net_total_pnl_bps"], label="M15", color="#059669")
    axes[0].axhline(0, color="#374151", lw=0.8)
    axes[0].set_title("Monthly Net Total (split thresholds, cost=5 bps)")
    axes[0].set_ylabel("Net total (bps)")
    axes[0].legend(loc="upper right")

    # Show net mean as secondary panel for context.
    axes[1].plot(m5_sub["month"], m5_sub["net_mean_pnl_bps"], label="M5", color="#2563eb")
    axes[1].plot(m15_sub["month"], m15_sub["net_mean_pnl_bps"], label="M15", color="#059669")
    axes[1].axhline(0, color="#374151", lw=0.8)
    axes[1].set_title("Monthly Net Mean (split thresholds, cost=5 bps)")
    axes[1].set_ylabel("Net mean (bps)")
    axes[1].legend(loc="upper right")

    axes[-1].set_xlabel("Month")
    fig.tight_layout()
    fig.savefig(fig_dir / "monthly_net_m5_m15.png", dpi=200)


if __name__ == "__main__":
    main()
