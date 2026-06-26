"""Does a burst EXTEND-trigger beat the static ffd_zvol20 threshold as the fade entry?

The reversion edge fades the ffd_zvol20 extension. Compare entry RULES, same payoff
(triple-barrier first-touch), same fade direction (-sign(ffd_zvol20) at entry), pooled 5
majors, walk-forward, non-overlap, cost, at N=20/30/50:

  STATIC q0.90 : enter when |ffd_zvol20| >= train top-decile          (current book)
  STATIC q0.99 : enter when |ffd_zvol20| >= train top-1%              (sharpened)
  EXTEND-burst : enter on a top-1% |return| burst that EXTENDS the deviation
                 (sign(burst) == sign(ffd_zvol20 just before))         (event trigger)
  EXTEND & hi  : EXTEND-burst AND already extended (|ffd_zvol20| >= train median-of-ext)

Report net/hit/folds+/sym+/n. Better = higher net AND breadth; n shows capacity.

Usage: uv run python scripts/fx_coint/entry_trigger_compare.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import build_all
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap
from scripts.fx_coint.triple_barrier import triple_barrier_core

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [20, 30, 50]
N_FOLDS = 5
COST = 1.0


def build(sym, n_tb):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    ev = np.arange(warm, n - n_tb - 3)
    ev = ev[np.isfinite(vol[ev + 1]) & (vol[ev + 1] > 0)]
    entry = ev + 1
    t1, y, _, _ = triple_barrier_core(logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
                                      1.0 * vol[entry] * np.sqrt(n_tb))
    r = np.append(np.nan, np.diff(logp)) * 1e4
    ar = np.abs(r)
    burst_thr = np.nanquantile(ar[np.isfinite(ar)], 0.99)
    return dict(
        entry=entry, t1=t1, y=y,
        ext=f["ffd_zvol20"][entry],                    # deviation at entry
        bmag=ar[entry], is_burst=(ar[entry] >= burst_thr),
        bdir=np.sign(r[entry]),
        ext_prev=f["ffd_zvol20"][entry - 1],
    )


def evaluate(data, select_fn, n_folds):
    syms = list(data)
    all_e = np.concatenate([data[s]["entry"] for s in syms])
    edges = np.quantile(all_e, np.linspace(0, 1, n_folds + 1))
    fnet, n_tr = [], 0
    sym_pos = np.zeros(len(syms))
    for k in range(1, n_folds):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = data[s]
            tr = d["entry"] < lo
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if tr.sum() < 300:
                continue
            sel = te & select_fn(d, tr) & np.isfinite(d["y"]) & np.isfinite(d["ext"]) & (d["ext"] != 0)
            if sel.sum() < 10:
                continue
            ent, t1 = d["entry"][sel], d["t1"][sel]
            direction = -np.sign(d["ext"][sel])         # fade the extension
            o = np.argsort(ent)
            keep = greedy_nonoverlap(ent[o], t1[o])
            pnl = (direction * d["y"][sel])[o][keep] - COST
            if len(pnl):
                fold.append(pnl)
                n_tr += len(pnl)
                if np.mean(pnl) > 0:
                    sym_pos[si] += 1
        if fold:
            fnet.append(np.mean(np.concatenate(fold)))
    fn = np.array(fnet)
    return dict(net=fn.mean() if len(fn) else np.nan, n=n_tr,
                folds_pos=int((fn > 0).sum()), nf=len(fn),
                sym_pos=int((sym_pos >= (n_folds - 1) / 2).sum()))


def main():
    for n_tb in N_GRID:
        data = {s: build(s, n_tb) for s in POOL}

        def static_q(d, tr, q):
            thr = np.nanquantile(np.abs(d["ext"][tr]), q)
            return np.abs(d["ext"]) >= thr

        def extend_burst(d, tr):
            return d["is_burst"] & (np.sign(d["bdir"]) == np.sign(d["ext_prev"]))

        def extend_hi(d, tr):
            thr = np.nanquantile(np.abs(d["ext"][tr]), 0.90)
            return extend_burst(d, tr) & (np.abs(d["ext"]) >= thr)

        rules = {
            "STATIC q0.90": lambda d, tr: static_q(d, tr, 0.90),
            "STATIC q0.99": lambda d, tr: static_q(d, tr, 0.99),
            "EXTEND-burst": extend_burst,
            "EXTEND & hi-ext": extend_hi,
        }
        print("=" * 78)
        print(f"ENTRY TRIGGER COMPARISON @N={n_tb} (fade ffd_zvol20, triple-barrier, cost={COST})")
        print("=" * 78)
        print(f"  {'rule':>16s} {'n':>7s} {'net':>7s} {'folds+':>7s} {'sym+':>5s}")
        for label, fn in rules.items():
            r = evaluate(data, fn, N_FOLDS)
            print(f"  {label:>16s} {r['n']:>7d} {r['net']:>+7.2f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5")
        print()


if __name__ == "__main__":
    main()
