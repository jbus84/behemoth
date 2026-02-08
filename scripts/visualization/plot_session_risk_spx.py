#!/usr/bin/env python3
"""
Plot session-level net mean for SPX (baseline model).
Outputs: docs/figures/session_risk_spx.png
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def _load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["model"] == "baseline_all_pairs"].copy()
    return df


def _prep(df: pd.DataFrame, edge: int) -> pd.DataFrame:
    sub = df[df["edge_threshold"] == edge].copy()
    order = ["Asia", "London", "New_York", "Late"]
    sub["session"] = pd.Categorical(sub["session"], order, ordered=True)
    sub = sub.sort_values("session")
    return sub[["session", "net_mean_pnl_bps"]]


def main() -> None:
    fig_dir = Path("docs/figures")
    fig_dir.mkdir(parents=True, exist_ok=True)

    m5 = _load("data/analysis/spx_m5_session_model_compare.csv")
    m15 = _load("data/analysis/spx_m15_session_model_compare.csv")

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, df, title in [(axes[0], m5, "M5 SPX Session Risk"), (axes[1], m15, "M15 SPX Session Risk")]:
        edge4 = _prep(df, 4)
        edge5 = _prep(df, 5)
        x = range(len(edge4))
        ax.bar([v - 0.18 for v in x], edge4["net_mean_pnl_bps"], width=0.35, label="edge>4")
        ax.bar([v + 0.18 for v in x], edge5["net_mean_pnl_bps"], width=0.35, label="edge>5")
        ax.set_xticks(list(x))
        ax.set_xticklabels(edge4["session"].astype(str))
        ax.axhline(0, color="#374151", lw=0.8)
        ax.set_title(title)
        ax.set_ylabel("Net mean (bps)")
        ax.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(fig_dir / "session_risk_spx.png", dpi=200)


if __name__ == "__main__":
    main()
