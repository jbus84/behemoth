#!/usr/bin/env python3
"""
Render the end-to-end pipeline overview diagram.
Outputs: docs/figures/pipeline_overview.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def _box(ax, xy, text, width=2.6, height=0.9):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2,
        edgecolor="#1f2937",
        facecolor="#e8f0fe",
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

    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    _box(ax, (0.6, 2.6), "Bar Data\n(global_5m / global_15m)")
    _box(ax, (3.4, 2.6), "Kalman Scout\n(beta, spread, Z-score)")
    _box(ax, (6.2, 2.6), "Meta Dataset\n(events_*_v3_dual.csv)")
    _box(ax, (0.6, 0.8), "Rule Engine\n(MOM + Guardrail)")
    _box(ax, (3.4, 0.8), "Z-Based Exit\n+ Guardrail Pause")
    _box(ax, (6.2, 0.8), "Trade Execution\n(active leg)")

    _arrow(ax, (3.2, 3.05), (3.4, 3.05))
    _arrow(ax, (5.9, 3.05), (6.2, 3.05))
    _arrow(ax, (7.5, 2.5), (7.5, 1.75))
    _arrow(ax, (3.2, 1.25), (3.4, 1.25))
    _arrow(ax, (5.9, 1.25), (6.2, 1.25))
    _arrow(ax, (1.9, 2.5), (1.9, 1.75))

    ax.text(
        0.6,
        3.7,
        "Rule-Based Pipeline (M5 / M15)",
        fontsize=11,
        fontweight="bold",
        color="#111827",
    )

    fig.tight_layout()
    fig.savefig(out_dir / "pipeline_overview.png", dpi=200)


if __name__ == "__main__":
    main()
