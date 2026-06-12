"""Visualise a Day-1 run: tape, filter, entries/exits, cumulative net P&L.

Top panel: raw mid (faint) with the Kalman micro-price over it, swing extrema marked,
and entry/exit arrows. Bottom panel: cumulative net pips. The eyeball test is "do entries
land near filtered-mid extrema and exits before the next reversal?"
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from scripts.era_tick.engine import EngineResult  # noqa: E402


def plot_run(result: EngineResult, out_path: Path, *, title: str = "") -> Path:
    trace = result.trace
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_px, ax_pnl) = plt.subplots(
        2, 1, figsize=(16, 9), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )

    x = trace["i"]
    ax_px.plot(x, trace["mid"], lw=0.4, color="0.7", label="raw mid")
    ax_px.plot(x, trace["mid_hat"], lw=0.9, color="C0", label="Kalman micro-price")

    # Swing extrema on the filtered line.
    for xi, mh, ex in zip(x, trace["mid_hat"], trace["extremum"]):
        if ex == "high":
            ax_px.plot(xi, mh, "v", color="0.4", ms=4)
        elif ex == "low":
            ax_px.plot(xi, mh, "^", color="0.4", ms=4)

    _plot_trades(ax_px, result)
    ax_px.set_ylabel("price")
    ax_px.legend(loc="upper left", fontsize=8)
    ax_px.set_title(title or f"{result.symbol} tick-by-tick fade — {len(result.trades)} trades")

    cum = _cumulative_net(result)
    ax_pnl.plot(cum["x"], cum["y"], lw=1.0, color="C2")
    ax_pnl.axhline(0.0, lw=0.6, color="0.6")
    ax_pnl.set_ylabel("cum net pips")
    ax_pnl.set_xlabel("tick index")

    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path


def _plot_trades(ax, result: EngineResult) -> None:
    for t in result.trades:
        e_color = "C2" if t.direction == 1 else "C3"
        ax.plot(t.entry_i, t.entry_mid, "o", color=e_color, ms=5)
        ax.plot(t.exit_i, t.exit_mid, "x", color="0.2", ms=5)
        ax.plot([t.entry_i, t.exit_i], [t.entry_mid, t.exit_mid], lw=0.6, color=e_color, alpha=0.5)


def _cumulative_net(result: EngineResult) -> dict[str, list]:
    xs, ys, run = [], [], 0.0
    for t in result.trades:
        run += t.net_pips
        xs.append(t.exit_i)
        ys.append(run)
    return {"x": xs, "y": ys}
