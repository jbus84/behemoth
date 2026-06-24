"""Do the structural/entropy features work as CONDITIONING GATES on the ffd
reversion signal (the dev_age pattern), rather than as additive features?

dev_age established the template: ffd's reversion IC is ~5x stronger in the OLD
(stale-deviation) tercile and that holds OOS — the feature's value is SELECTION,
not additive IC. This generalizes that test to every candidate gate:

  for each gate G, split events into terciles of G (thresholds fit on TRAIN only),
  and measure the ffd->target reversion IC within each tercile, IS and OOS, pooled
  over the 5 ex-JPY majors. A useful gate concentrates the reversion edge in one
  tercile, OOS.

Target: N-bar triple-barrier reversion (long N where reversion lives). Reuses the
full feature build (incl. De Prado price-only) from feature_ic_definitive.

Usage: uv run python scripts/fx_coint/reversion_gate_scan.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [30, 50]
N_EVENTS = 40000
TRAIN_FRAC = 0.70
BASE = "ffd_0.1"
GATES = ["dev_age", "ent_sign", "cusum_csw", "smt_exp", "adf_sup"]
TERCILES = [("T1 (low)", 0.0, 0.34), ("T2 (mid)", 0.33, 0.67), ("T3 (high)", 0.66, 1.0)]
OUT = Path("reports/reversion_gate_scan")


def _ic(base, y):
    ok = np.isfinite(base) & np.isfinite(y)
    return stats.spearmanr(base[ok], y[ok])[0] if ok.sum() > 200 else np.nan


def _tercile_ic(base, g, y, lo, hi, thr_lo, thr_hi):
    m = (g >= thr_lo) & (g <= thr_hi) & np.isfinite(base) & np.isfinite(y) & np.isfinite(g)
    return stats.spearmanr(base[m], y[m])[0] if m.sum() > 200 else np.nan


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

    results = {}  # (N, gate) -> dict of arrays
    for n_tb in N_GRID:
        targ = {}
        for s in POOL:
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            entry = ev + 1
            vert = np.minimum(entry + n_tb, len(logp) - 1)
            _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(n_tb))
            targ[s] = y
        # unconditional OOS reference
        unc_oos = []
        for s in POOL:
            _, f, _, _ = cache[s]
            ev = evset[s]
            cut = int(len(ev) * TRAIN_FRAC)
            unc_oos.append(_ic(f[BASE][ev][cut:], targ[s][cut:]))
        unc_oos = np.array(unc_oos)

        for g in GATES:
            is_ic = {lab: [] for lab, _, _ in TERCILES}
            oos_ic = {lab: [] for lab, _, _ in TERCILES}
            for s in POOL:
                _, f, _, _ = cache[s]
                ev = evset[s]
                base, gate, y = f[BASE][ev], f[g][ev], targ[s]
                cut = int(len(ev) * TRAIN_FRAC)
                gtr = gate[:cut]
                gtr = gtr[np.isfinite(gtr)]
                for lab, lo, hi in TERCILES:
                    tl, th = np.quantile(gtr, lo), np.quantile(gtr, hi)
                    is_ic[lab].append(_tercile_ic(base[:cut], gate[:cut], y[:cut], lo, hi, tl, th))
                    oos_ic[lab].append(_tercile_ic(base[cut:], gate[cut:], y[cut:], lo, hi, tl, th))
            results[(n_tb, g)] = dict(
                unc_oos=unc_oos,
                is_ic={k: np.array(v) for k, v in is_ic.items()},
                oos_ic={k: np.array(v) for k, v in oos_ic.items()})

    # ---- report ----
    print("=" * 96)
    print("REVERSION-GATE SCAN — ffd reversion IC within terciles of each gate "
          "(pooled 5 ex-JPY majors)")
    print("  thresholds fit on TRAIN; IS=train, OOS=chrono 30% holdout; reversion IC is NEGATIVE")
    print("=" * 96)
    for n_tb in N_GRID:
        unc = results[(n_tb, GATES[0])]["unc_oos"]
        print(f"\n### N = {n_tb}    unconditional OOS ffd IC = {np.nanmean(unc):+.4f}")
        print(f"  {'gate':12s} {'tercile':10s} {'IS IC':>8s} {'OOS IC':>8s} {'sign':>6s} "
              f"{'OOS/unc':>8s}")
        for g in GATES:
            r = results[(n_tb, g)]
            for lab, _, _ in TERCILES:
                o = r["oos_ic"][lab]
                i = r["is_ic"][lab]
                sgn = int((np.sign(o) == np.sign(np.nanmean(o))).sum())
                ratio = np.nanmean(o) / np.nanmean(unc) if np.nanmean(unc) != 0 else np.nan
                print(f"  {g:12s} {lab:10s} {np.nanmean(i):8.4f} {np.nanmean(o):8.4f} {sgn:>4d}/5 "
                      f"{ratio:8.2f}")
            print()

    # ---- plot: OOS ffd-IC by tercile, one panel per gate, per N ----
    for n_tb in N_GRID:
        unc = np.nanmean(results[(n_tb, GATES[0])]["unc_oos"])
        fig, axes = plt.subplots(1, len(GATES), figsize=(3.2 * len(GATES), 4), sharey=True)
        labs = [t[0] for t in TERCILES]
        for ax, g in zip(axes, GATES, strict=False):
            r = results[(n_tb, g)]
            vals = [np.nanmean(r["oos_ic"][lab]) for lab in labs]
            ax.bar(labs, vals, color=["#4c72b0", "#999999", "#c44e52"])
            ax.axhline(unc, color="k", linestyle="--", linewidth=1, label="unconditional")
            ax.set_title(g, fontsize=10)
            ax.tick_params(axis="x", labelrotation=30, labelsize=8)
            ax.grid(axis="y", alpha=0.3)
        axes[0].set_ylabel("OOS ffd reversion IC")
        axes[-1].legend(fontsize=8)
        fig.suptitle(f"Reversion-gate scan — OOS ffd IC by gate tercile (N={n_tb}, dashed = unconditional)")
        fig.tight_layout()
        fig.savefig(OUT / f"gate_oos_ic_N{n_tb}.png", dpi=110)
        plt.close(fig)
    print(f"\nplots -> {OUT}")


if __name__ == "__main__":
    main()
