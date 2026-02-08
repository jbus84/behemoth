#!/usr/bin/env python3
"""
Render decision flow diagram for MOM-only two-stage model.
Outputs: docs/figures/decision_flow.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def _box(ax, xy, text, width=3.0, height=0.9, color="#ecfccb"):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2,
        edgecolor="#1f2937",
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=9)


def _arrow(ax, start, end):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(arrowstyle="->", lw=1.2, color="#374151"),
    )


def main() -> None:
    out_dir = Path("docs/figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.6)
    ax.axis("off")

    _box(ax, (0.6, 2.2), "Stage 1: Classifier\np_up = P(MOM win)")
    _box(ax, (0.6, 0.6), "Stage 2: Regressor\npred_pnl = E[PnL]")
    _box(ax, (4.2, 1.4), "Edge Score\npred_pnl (expected value)")
    _box(ax, (7.2, 1.4), "Decision\np_up>=0.5 AND edge > threshold\nTrade MOM (REV disabled)")

    _arrow(ax, (3.6, 2.65), (4.2, 1.95))
    _arrow(ax, (3.6, 1.05), (4.2, 1.95))
    _arrow(ax, (6.8, 1.95), (7.2, 1.95))

    ax.text(
        0.6,
        3.1,
        "Two-Stage Decision Logic",
        fontsize=11,
        fontweight="bold",
        color="#111827",
    )

    fig.tight_layout()
    fig.savefig(out_dir / "decision_flow.png", dpi=200)


if __name__ == "__main__":
    main()
