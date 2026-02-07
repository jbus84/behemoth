#!/usr/bin/env python3
"""
Plot monthly net and drawdown curves for baseline vs guardrail.

Outputs:
 - docs/figures/m5_guardrail_monthly_net.png
 - docs/figures/m5_guardrail_drawdown.png
 - docs/figures/m15_guardrail_monthly_net.png
 - docs/figures/m15_guardrail_drawdown.png
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

FIG_DIR = Path("docs/figures")

FILES = {
    "m5": "data/analysis/m5_guardrail_monthly.csv",
    "m15": "data/analysis/m15_guardrail_monthly.csv",
}


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["year_month"] = pd.to_datetime(out["year_month"], format="%Y-%m")
    out = out.sort_values("year_month")
    return out


def _plot_monthly(df: pd.DataFrame, label: str) -> None:
    plt.figure(figsize=(9, 4.5))
    for variant, sub in df.groupby("variant"):
        plt.plot(sub["year_month"], sub["total_pnl"].cumsum(), label=variant)
    plt.title(f"{label.upper()} Monthly Net PnL (Baseline vs Guardrail)")
    plt.ylabel("Cumulative PnL (bps)")
    plt.xlabel("Month")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / f"{label}_guardrail_monthly_net.png", dpi=200)
    plt.close()


def _plot_dd(df: pd.DataFrame, label: str) -> None:
    plt.figure(figsize=(9, 4.5))
    for variant, sub in df.groupby("variant"):
        curve = sub["total_pnl"].cumsum()
        peak = curve.cummax()
        dd = curve - peak
        plt.plot(sub["year_month"], dd, label=variant)
    plt.title(f"{label.upper()} Drawdown (Baseline vs Guardrail)")
    plt.ylabel("Drawdown (bps)")
    plt.xlabel("Month")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / f"{label}_guardrail_drawdown.png", dpi=200)
    plt.close()


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for label, path in FILES.items():
        if not os.path.exists(path):
            print(f"Missing {path}, skipping {label}")
            continue
        df = _prep(pd.read_csv(path))
        _plot_monthly(df, label)
        _plot_dd(df, label)
    print("Saved plots to docs/figures/")


if __name__ == "__main__":
    main()
