"""Threshold to the LARGEST moves — does the extreme tail become tradeable?

We've used top-decile (q0.90). The extreme tail is different: moves are huge so the
breakeven hit-rate collapses, and the largest extensions may revert hardest (or the
largest impulses may ignite/continue). Test both behaviours at increasing extremity.

Two signals, causal walk-forward thresholds, non-overlap, real cost, pooled 5 majors:
  IMPULSE   = vol-normalised recent w-bar move (the 'big move' just happened)
  REVSIG    = ffd_zvol20 (the validated reversion extension)
For thresholds q in {0.90, 0.99, 0.995, 0.999}:
  FADE  REVSIG  at N=50  (mega-reversion?)         -> net, hit vs breakeven, |move|
  FOLLOW IMPULSE at N=3  (momentum ignition?)      -> net, hit vs breakeven, |move|
A positive net at the tail = the largest moves are tradeable where the bulk isn't.

Usage: uv run python scripts/fx_coint/extreme_move_probe.py
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
N_EVENTS = 60000
N_FOLDS = 5
COST = 1.0
QS = [0.90, 0.99, 0.995, 0.999]
IMP_W = 5          # recent-move window for the impulse


def build(sym):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    idx = np.arange(warm, n - 51 - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    rng = np.random.default_rng(0)
    ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    # vol-normalised recent w-bar move (signed impulse)
    rec = (logp[ev] - logp[ev - IMP_W]) * 1e4
    imp = rec / (vol[ev] * 1e4 * np.sqrt(IMP_W) + 1e-9)
    revsig = f["ffd_zvol20"][ev]
    fwd3 = (logp[ev + 3] - logp[ev]) * 1e4
    t1_50, y50, _, _ = triple_barrier_core(logp, ev, np.minimum(ev + 50, len(logp) - 1),
                                           1.0 * vol[ev] * np.sqrt(50))
    return dict(entry=ev, imp=imp, revsig=revsig, fwd3=fwd3, y50=y50, t150=t1_50)


def run(panel, sigkey, fade, horizon_key, t1key, q):
    """Fade (or follow) signal at threshold q, non-overlap, walk-forward; net/hit/move."""
    syms = list(panel)
    all_e = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_e, np.linspace(0, 1, N_FOLDS + 1))
    fnet, moves, hits, ntr = [], [], [], 0
    sym_pos = np.zeros(len(syms))
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = panel[s]
            tr = d["entry"] < lo
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            sig = d[sigkey]
            ok_tr = tr & np.isfinite(sig)
            if ok_tr.sum() < 300:
                continue
            thr = np.nanquantile(np.abs(sig[ok_tr]), q)
            y = d[horizon_key]
            sel = te & np.isfinite(sig) & np.isfinite(y) & (np.abs(sig) >= thr)
            if sel.sum() < 5:
                continue
            sign = -np.sign(sig[sel]) if fade else np.sign(sig[sel])
            ent, t1 = d["entry"][sel], d[t1key][sel] if t1key else d["entry"][sel] + 3
            o = np.argsort(ent)
            keep = greedy_nonoverlap(ent[o], t1[o])
            pnl = (sign[o][keep] * y[sel][o][keep])
            mv = np.abs(y[sel][o][keep])
            if len(pnl):
                fold.append(pnl - COST)
                moves.append(mv)
                hits.append((pnl > 0).astype(float))
                ntr += len(pnl)
                if np.mean(pnl - COST) > 0:
                    sym_pos[si] += 1
        if fold:
            fnet.append(np.mean(np.concatenate(fold)))
    fn = np.array(fnet)
    mv = np.mean(np.concatenate(moves)) if moves else np.nan
    hit = np.mean(np.concatenate(hits)) if hits else np.nan
    bh = 0.5 + COST / (2 * mv) if mv and np.isfinite(mv) else np.nan
    return dict(net=fn.mean() if len(fn) else np.nan, hit=hit, move=mv, bh=bh, ntr=ntr,
                folds_pos=int((fn > 0).sum()), nf=len(fn),
                sym_pos=int((sym_pos >= (N_FOLDS - 1) / 2).sum()))


def main():
    panel = {s: build(s) for s in POOL}
    print(f"Extreme-move thresholding | pooled 5 majors | cost={COST}")
    print("\nFADE ffd_zvol20 @N=50 (mega-reversion at the tail?)")
    print(f"  {'q':>6s} {'nTr':>7s} {'|move|':>7s} {'breakHit':>8s} {'hit':>6s} {'net':>7s} {'folds+':>7s} {'sym+':>5s}")
    for q in QS:
        r = run(panel, "revsig", True, "y50", "t150", q)
        print(f"  {q:>6.3f} {r['ntr']:>7d} {r['move']:>7.2f} {r['bh']:>8.3f} {r['hit']:>6.3f} "
              f"{r['net']:>+7.2f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5")

    print("\nFOLLOW recent-move IMPULSE @N=3 (momentum ignition at the tail?)")
    print(f"  {'q':>6s} {'nTr':>7s} {'|move|':>7s} {'breakHit':>8s} {'hit':>6s} {'net':>7s} {'folds+':>7s} {'sym+':>5s}")
    for q in QS:
        r = run(panel, "imp", False, "fwd3", None, q)
        print(f"  {q:>6.3f} {r['ntr']:>7d} {r['move']:>7.2f} {r['bh']:>8.3f} {r['hit']:>6.3f} "
              f"{r['net']:>+7.2f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5")

    print("\nFADE recent-move IMPULSE @N=3 (extreme impulse reverts fast?)")
    print(f"  {'q':>6s} {'nTr':>7s} {'|move|':>7s} {'breakHit':>8s} {'hit':>6s} {'net':>7s} {'folds+':>7s} {'sym+':>5s}")
    for q in QS:
        r = run(panel, "imp", True, "fwd3", None, q)
        print(f"  {q:>6.3f} {r['ntr']:>7d} {r['move']:>7.2f} {r['bh']:>8.3f} {r['hit']:>6.3f} "
              f"{r['net']:>+7.2f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5")


if __name__ == "__main__":
    main()
