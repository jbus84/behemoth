"""Next-bar (very short N) tradeability: does thresholding rescue it?

N=1..3 has the densest, lowest-overlap signal (at N=1 every event is independent)
but the smallest moves. This measures realized walk-forward non-overlap net bps for
the short-N-appropriate base signals, swept over conviction THRESHOLD (top-quantile
of |signal|) and cost, to test whether isolating high-conviction predictions clears
cost where the full sample does not.

Signals (short-N leaders from the definitive IC study), with trade direction:
  ffd_demean20  fade (reversion)    pos = -sign(signal)
  ffd_vel5      fade (reversion)    pos = -sign(signal)
  ffd_zvol20    fade (reference)    pos = -sign(signal)
  intra_bar_mom continuation        pos = +sign(signal)

Cost scenarios (round-trip bps): 1.0 = taker (realistic); 0.0 / -0.5 = MAKER, but
OPTIMISTIC — this lowers cost WITHOUT modelling adverse selection (you tend to get
filled when wrong), so maker rows are an upper bound, not a tradeable estimate.

Thresholds fit on train only; walk-forward expanding folds; non-overlap trades only.

Usage: uv run python scripts/fx_coint/pnl_nextbar.py
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
from pnl_walkforward import greedy_nonoverlap  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [1, 2, 3]
N_EVENTS = 40000
N_FOLDS = 5
SIGNALS = {"ffd_demean20": -1, "ffd_vel5": -1, "ffd_zvol20": -1, "intra_bar_mom": +1}
QS = [0.0, 0.90, 0.95, 0.99]          # conviction threshold on |signal| (train)
COSTS = [1.0, 0.0, -0.5]              # 1.0 taker; 0.0/-0.5 maker (optimistic)
OUT = Path("reports/pnl_nextbar")


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

    curves = {}   # (signal, N, q) -> dict(gross, nets per cost, folds_pos, sym_pos, n)
    for sig, mult in SIGNALS.items():
        for n_tb in N_GRID:
            sym_d = {}
            for s in POOL:
                logp, f, vol, bph = cache[s]
                ev = evset[s]
                entry = ev + 1
                vert = np.minimum(entry + n_tb, len(logp) - 1)
                t1, ret, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
                g = f[sig][ev]
                pnl = mult * np.sign(g) * ret      # fade (-1) or continuation (+1)
                sym_d[s] = dict(entry=entry, t1=t1, pnl=pnl, sig=g)
            all_entry = np.concatenate([sym_d[s]["entry"] for s in POOL])
            edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))
            for q in QS:
                fold_gross, n_trades, sym_pos = [], 0, np.zeros(len(POOL))
                for k in range(1, N_FOLDS):
                    lo, hi = edges[k], edges[k + 1]
                    fold = []
                    for si, s in enumerate(POOL):
                        d = sym_d[s]
                        tr = d["entry"] < lo
                        te = (d["entry"] >= lo) & (d["entry"] < hi)
                        if tr.sum() < 200 or te.sum() < 20:
                            continue
                        thr = np.nanquantile(np.abs(d["sig"][tr]), q) if q > 0 else -np.inf
                        sel = te & (np.abs(d["sig"]) >= thr) & np.isfinite(d["pnl"])
                        order = np.argsort(d["entry"][sel])
                        ko = greedy_nonoverlap(d["entry"][sel][order], d["t1"][sel][order])
                        p = d["pnl"][sel][order][ko]
                        if len(p):
                            fold.append(p)
                            n_trades += len(p)
                            if np.mean(p) > 0:
                                sym_pos[si] += 1
                    if fold:
                        fold_gross.append(np.mean(np.concatenate(fold)))
                fold_gross = np.array(fold_gross)
                gross = float(np.mean(fold_gross)) if len(fold_gross) else float("nan")
                curves[(sig, n_tb, q)] = dict(
                    gross=gross,
                    nets={c: gross - c for c in COSTS},
                    folds_pos=int((fold_gross - 1.0 > 0).sum()),   # folds+ at taker cost
                    sym_pos=int((sym_pos >= (N_FOLDS - 1) / 2).sum()),
                    n=n_trades)

    print("=" * 104)
    print("NEXT-BAR NET-P&L — short-N base signals, walk-forward non-overlap, conviction sweep")
    print("  cost 1.0=taker | 0.0/-0.5=maker(OPTIMISTIC, no adverse-selection) | folds+ at taker")
    print("=" * 104)
    print(f"  {'signal':14s} {'N':>2s} {'q':>5s} {'trades':>8s} {'gross':>8s} "
          f"{'net@1.0':>8s} {'net@0.0':>8s} {'net@-.5':>8s} {'fld+':>5s} {'sym+':>5s}")
    for sig in SIGNALS:
        for n_tb in N_GRID:
            for q in QS:
                c = curves[(sig, n_tb, q)]
                print(f"  {sig:14s} {n_tb:>2d} {q:>5.2f} {c['n']:>8d} {c['gross']:+8.4f} "
                      f"{c['nets'][1.0]:+8.4f} {c['nets'][0.0]:+8.4f} {c['nets'][-0.5]:+8.4f} "
                      f"{c['folds_pos']:>3d}/4 {c['sym_pos']:>3d}/5")
            print()

    # plot: gross bps vs threshold q, per signal, one panel per N
    fig, axes = plt.subplots(1, len(N_GRID), figsize=(4.2 * len(N_GRID), 4.2), sharey=True)
    for ax, n_tb in zip(axes, N_GRID, strict=False):
        for sig in SIGNALS:
            ax.plot(QS, [curves[(sig, n_tb, q)]["gross"] for q in QS], marker="o", label=sig, linewidth=1.6)
        ax.axhline(1.0, color="r", ls="--", lw=1, label="taker cost")
        ax.axhline(0.0, color="k", lw=1)
        ax.set_title(f"N={n_tb}")
        ax.set_xlabel("conviction threshold q (|signal| quantile)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("gross bps/trade")
    axes[-1].legend(fontsize=7)
    fig.suptitle("Next-bar gross bps/trade vs conviction threshold (above red dashed = beats taker cost)")
    fig.tight_layout()
    fig.savefig(OUT / "nextbar_gross_vs_threshold.png", dpi=110)
    plt.close(fig)
    print(f"plot -> {OUT / 'nextbar_gross_vs_threshold.png'}")


if __name__ == "__main__":
    main()
