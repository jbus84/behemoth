"""Decisive tradeability gate: NON-OVERLAPPING trades + WALK-FORWARD.

pnl_assessment showed gated+top_mag net-positive after cost on a single chrono
split, but on overlapping trades. This is the mirage-killer: it (1) selects only
NON-OVERLAPPING trades (next entry >= previous trade's first-touch exit, so every
P&L draw is independent), and (2) evaluates over EXPANDING walk-forward folds with
selection thresholds fit only on data before each fold.

Strategy unchanged: fade ffd_zvol20, payoff = triple-barrier first-touch return.
Reports per (N, isolation): independent trade count, mean net bps/trade at real
cost, fraction of walk-forward folds positive, fraction of symbols positive.

Usage: uv run python scripts/fx_coint/pnl_walkforward.py
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
SIGNAL = "ffd_zvol20"
COST = 1.0          # round-trip bps (realistic Razor-type)
N_FOLDS = 5
ISOLATIONS = ["top_mag", "gated+top_mag"]
OUT = Path("reports/pnl_walkforward")


def _greedy_nonoverlap(entry, t1):
    """Keep trades whose entry is at/after the previous kept trade's exit (t1).
    entry/t1 are time-sorted index arrays; returns a boolean keep-mask."""
    keep = np.zeros(len(entry), dtype=bool)
    last_exit = -1
    for i in range(len(entry)):
        if entry[i] >= last_exit:
            keep[i] = True
            last_exit = t1[i]
    return keep


def _select(iso, sig, age, adf, thr):
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

    fold_curves = {}    # (N, iso) -> array of per-fold pooled net bps
    for n_tb in N_GRID:
        print("=" * 92)
        print(f"WALK-FORWARD NON-OVERLAP NET-P&L — fade {SIGNAL}, N={n_tb}, cost={COST}bps round-trip")
        print(f"  {N_FOLDS} expanding folds | independent trades only | pooled 5 majors")
        print("=" * 92)
        print(f"  {'isolation':16s} {'indep_trades':>12s} {'net bps':>9s} {'folds+':>7s} {'sym+':>6s}")
        for iso in ISOLATIONS:
            # gather per-symbol selected, non-overlapping trades with timestamps
            sym_trades = {}
            for s in POOL:
                logp, f, vol, bph = cache[s]
                ev = evset[s]
                entry = ev + 1
                t1arr, y, _, _ = triple_barrier_core(
                    logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
                    1.0 * vol[entry] * np.sqrt(n_tb))
                sig, age, adf = f[SIGNAL][ev], f["dev_age"][ev], f["adf_sup"][ev]
                # thresholds fit on first 40% (pre-walk-forward burn-in); refit per fold below
                pnl = -np.sign(sig) * y
                sym_trades[s] = dict(entry=entry, t1=t1arr, sig=sig, age=age, adf=adf, pnl=pnl)

            # expanding walk-forward over the time axis (shared bar-index folds)
            all_entry = np.concatenate([sym_trades[s]["entry"] for s in POOL])
            edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))
            fold_net, n_indep, sym_pos = [], 0, np.zeros(len(POOL))
            for k in range(1, N_FOLDS):
                lo, hi = edges[k], edges[k + 1]
                fold_pnls = []
                for si, s in enumerate(POOL):
                    d = sym_trades[s]
                    tr = d["entry"] < lo            # train = everything before fold
                    te = (d["entry"] >= lo) & (d["entry"] < hi)
                    if tr.sum() < 200 or te.sum() < 20:
                        continue
                    thr = dict(
                        mag=np.nanquantile(np.abs(d["sig"][tr]), 0.90),
                        age_hi=np.nanquantile(d["age"][tr], 0.66),
                        adf_lo=np.nanquantile(d["adf"][tr], 0.34))
                    sel = _select(iso, d["sig"], d["age"], d["adf"], thr) & te & np.isfinite(d["pnl"])
                    order = np.argsort(d["entry"][sel])
                    e_sel, t_sel, p_sel = d["entry"][sel][order], d["t1"][sel][order], d["pnl"][sel][order]
                    ko = _greedy_nonoverlap(e_sel, t_sel)
                    p = p_sel[ko] - COST
                    if len(p):
                        fold_pnls.append(p)
                        n_indep += len(p)
                        if np.mean(p) > 0:
                            sym_pos[si] += 1
                if fold_pnls:
                    fold_net.append(np.mean(np.concatenate(fold_pnls)))
            fold_net = np.array(fold_net)
            fold_curves[(n_tb, iso)] = fold_net
            folds_pos = int((fold_net > 0).sum())
            # a symbol counts as + if positive in a majority of folds it appeared
            sym_plus = int((sym_pos >= (N_FOLDS - 1) / 2).sum())
            print(f"  {iso:16s} {n_indep:>12d} {np.mean(fold_net):+9.3f} "
                  f"{folds_pos:>4d}/{len(fold_net)} {sym_plus:>4d}/5")
        print()

    # plot: per-fold net bps (walk-forward stability) for gated+top_mag
    fig, ax = plt.subplots(figsize=(9, 5))
    for n_tb in N_GRID:
        fc = fold_curves.get((n_tb, "gated+top_mag"))
        if fc is not None and len(fc):
            ax.plot(range(1, len(fc) + 1), fc, marker="o", label=f"N={n_tb}", linewidth=1.7)
    ax.axhline(0, color="k", linewidth=1)
    ax.set_xlabel("walk-forward fold (chronological)")
    ax.set_ylabel(f"net bps/trade (cost={COST})")
    ax.set_title("Walk-forward non-overlap net P&L — gated+top_mag (fade ffd_zvol20)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "walkforward_net_pnl.png", dpi=110)
    plt.close(fig)
    print(f"plot -> {OUT / 'walkforward_net_pnl.png'}")


if __name__ == "__main__":
    main()
