#!/usr/bin/env python3
"""
Render a feature flow diagram (signals -> feature blocks -> model).
Outputs: docs/figures/feature_flow.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def _box(ax, xy, text, width=2.8, height=0.9, color="#fef3c7"):
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

    fig, ax = plt.subplots(figsize=(10.5, 4.5))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4.5)
    ax.axis("off")

    _box(ax, (0.6, 3.0), "Kalman Outputs\n(beta, spread, Z)")
    _box(ax, (0.6, 1.6), "Trade Context\n(time, returns, ATR)")
    _box(ax, (4.0, 3.0), "Signal Quality\nz_entry, z_velocity,\nspread_std")
    _box(ax, (4.0, 1.6), "Regime\nbeta, vol_ratio,\ncorrelation, trend")
    _box(ax, (7.4, 2.3), "Feature Vector\n(categorical + numeric)")
    _box(ax, (9.6, 2.3), "Two-Stage Model")

    _arrow(ax, (3.2, 3.45), (4.0, 3.45))
    _arrow(ax, (3.2, 2.05), (4.0, 2.05))
    _arrow(ax, (6.8, 3.45), (7.4, 2.75))
    _arrow(ax, (6.8, 2.05), (7.4, 2.75))
    _arrow(ax, (9.2, 2.75), (9.6, 2.75))

    ax.text(
        0.6,
        4.1,
        "Feature Flow (M5 / M15)",
        fontsize=11,
        fontweight="bold",
        color="#111827",
    )

    fig.tight_layout()
    fig.savefig(out_dir / "feature_flow.png", dpi=200)


if __name__ == "__main__":
    main()
