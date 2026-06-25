"""Is the gated reversion signal actually TRADEABLE? Net-P&L assessment.

IC is a rank statistic that hides magnitude and cost. This converts the signal
into realized per-trade P&L: the triple-barrier first-touch return IS the trade
outcome in bps, so the fade strategy's gross P&L is just

    pnl_bps = -sign(ffd_zvol20) * first_touch_return_bps        (fade the deviation)

evaluated OOS (chrono 30% holdout; selection thresholds fit on train only),
pooled over 5 ex-JPY majors, net of a swept round-trip cost.

"Isolate stronger moves" is the lever, tested four ways:
  all            : every event
  top_mag        : top-decile |ffd_zvol20| (magnitude conviction)
  gated          : stale (dev_age T3) AND stable (adf_sup T1)  -- avoid explosive cells
  gated+top_mag  : both

Reports per (N, isolation): trades, gross bps/trade, hit rate, per-symbol sign,
net bps/trade at each cost, and the BREAKEVEN cost (= gross bps/trade).

Usage: uv run python scripts/fx_coint/pnl_assessment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [10, 20, 30, 50]
N_EVENTS = 40000
TRAIN_FRAC = 0.70
SIGNAL = "ffd_zvol20"
COST_GRID = [0.0, 0.5, 1.0, 1.5, 2.0]   # round-trip bps
ISOLATIONS = ["all", "top_mag", "gated", "gated+top_mag"]
OUT = Path("reports/pnl_assessment")


def _mask(iso, sig, age, adf, thr):
    keep = np.isfinite(sig)
    if "top_mag" in iso:
        keep &= np.abs(sig) >= thr["mag"]
    if "gated" in iso:
        keep &= (age >= thr["age_hi"]) & (adf <= thr["adf_lo"])
    return keep


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(N_GRID) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    grid_net = {}   # (N, iso) -> {cost: net}; plus gross / hit / sign / n
    for n_tb in N_GRID:
        per_iso = {iso: dict(pnl=[], n=0, possym=0) for iso in ISOLATIONS}
        for s in POOL:
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            entry = ev + 1
            vert = np.minimum(entry + n_tb, len(logp) - 1)
            _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
            sig, age, adf = f[SIGNAL][ev], f["dev_age"][ev], f["adf_sup"][ev]
            cut = int(len(ev) * TRAIN_FRAC)
            thr = dict(
                mag=np.nanquantile(np.abs(sig[:cut]), 0.90),
                age_hi=np.nanquantile(age[:cut], 0.66),
                adf_lo=np.nanquantile(adf[:cut], 0.34))
            st, yt = slice(cut, None), y[cut:]
            sg, ag, ad = sig[st], age[st], adf[st]
            gross = -np.sign(sg) * yt          # fade the deviation, bps
            for iso in ISOLATIONS:
                m = _mask(iso, sg, ag, ad, thr) & np.isfinite(yt)
                pnl = gross[m]
                per_iso[iso]["pnl"].append(pnl)
                per_iso[iso]["n"] += len(pnl)
                if len(pnl) and np.nanmean(pnl) > 0:
                    per_iso[iso]["possym"] += 1
        print("=" * 96)
        print(f"NET-P&L — fade ffd_zvol20, N={n_tb} TB, OOS (chrono 30% holdout), pooled 5 majors")
        print("=" * 96)
        print(f"  {'isolation':14s} {'trades':>8s} {'gross':>8s} {'hit%':>6s} {'+sym':>5s}   "
              + "  ".join(f"net@{c}" for c in COST_GRID))
        for iso in ISOLATIONS:
            allp = np.concatenate(per_iso[iso]["pnl"]) if per_iso[iso]["pnl"] else np.array([])
            if len(allp) == 0:
                continue
            gross = np.nanmean(allp)
            hit = np.mean(allp > 0) * 100
            nets = {c: gross - c for c in COST_GRID}
            grid_net[(n_tb, iso)] = dict(gross=gross, nets=nets)
            netstr = "  ".join(f"{nets[c]:+6.3f}" for c in COST_GRID)
            print(f"  {iso:14s} {per_iso[iso]['n']:>8d} {gross:+8.3f} {hit:6.1f} "
                  f"{per_iso[iso]['possym']:>3d}/5   {netstr}")
        print("  (breakeven round-trip cost = gross bps/trade; reversion fade, unit size)\n")

    # plot: net bps/trade vs cost, per isolation, one panel per N
    fig, axes = plt.subplots(1, len(N_GRID), figsize=(4 * len(N_GRID), 4.2), sharey=True)
    for ax, n_tb in zip(axes, N_GRID, strict=False):
        for iso in ISOLATIONS:
            if (n_tb, iso) in grid_net:
                nets = grid_net[(n_tb, iso)]["nets"]
                ax.plot(COST_GRID, [nets[c] for c in COST_GRID], marker="o", label=iso, linewidth=1.6)
        ax.axhline(0, color="k", linewidth=1)
        ax.set_title(f"N={n_tb}")
        ax.set_xlabel("round-trip cost (bps)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("net bps / trade")
    axes[-1].legend(fontsize=8)
    fig.suptitle("Tradeability — net bps/trade vs cost (fade ffd_zvol20, OOS). Above 0 = profitable.")
    fig.tight_layout()
    fig.savefig(OUT / "net_pnl_vs_cost.png", dpi=110)
    plt.close(fig)
    print(f"plot -> {OUT / 'net_pnl_vs_cost.png'}")


if __name__ == "__main__":
    main()
