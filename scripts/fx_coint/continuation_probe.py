"""Continuation-before-reversion: map the impulse -> continuation -> reversion curve.

Reversion corrects an overshoot, so an impulse/continuation phase must precede it. We
harvest reversion at N=20-50; this tests the FRONT of the move: conditional on a fresh
IMPULSE (top-decile recent move), does FOLLOWING it pay at very short horizons before it
reverts — and does the continuation move clear cost?

For several impulse definitions, pooled over 5 ex-JPY majors on 1000-tick bars:
  1. CROSSOVER MAP: mean(sign(impulse) * fwd_N return) for N=1,2,3,5,10,20,50.
     Positive = continuation, negative = reversion; find where it flips.
  2. CONTINUATION NET: among top-decile |impulse| events (the strong impulses), follow
     the impulse for N bars, non-overlap, real cost; report gross |move|, hit-rate vs
     breakeven, net, folds+/sym+. (Is the impulse big enough + callable enough to trade?)

Usage: uv run python scripts/fx_coint/continuation_probe.py
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

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [1, 2, 3, 5, 10, 20, 50]
N_EVENTS = 40000
N_FOLDS = 5
COST = 1.0
# impulse definitions (sign = direction of the impulse)
IMPULSES = ["bar_return_sign", "ffd_vel5", "intra_bar_mom", "macd"]


def build(sym):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    idx = np.arange(warm, n - max(N_GRID) - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    rng = np.random.default_rng(0)
    ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    fwd = {N: (logp[ev + N] - logp[ev]) * 1e4 for N in N_GRID}
    return dict(ev=ev, fwd=fwd, feat={k: f[k][ev] for k in IMPULSES}, logp=logp)


def main():
    data = {s: build(s) for s in POOL}

    print("CROSSOVER MAP — mean(sign(impulse)*fwd_N) bps, pooled (>0=continuation, <0=reversion)")
    print(f"  {'impulse':>16s} " + " ".join(f"N{N:>5d}" for N in N_GRID))
    for imp in IMPULSES:
        row = []
        for N in N_GRID:
            vals = []
            for s in POOL:
                d = data[s]
                sig = d["feat"][imp]
                y = d["fwd"][N]
                m = np.isfinite(sig) & np.isfinite(y) & (sig != 0)
                vals.append(np.sign(sig[m]) * y[m])
            allv = np.concatenate(vals)
            row.append(np.mean(allv))
        print(f"  {imp:>16s} " + " ".join(f"{v:>+6.2f}" for v in row))

    print("\nCONTINUATION NET — follow top-decile |impulse|, non-overlap, cost=1.0 "
          "(|move|=gross bps, hit vs breakeven)")
    print(f"  {'impulse':>16s} {'N':>3s} {'|move|':>7s} {'breakHit':>8s} {'hit':>6s} "
          f"{'net':>7s} {'folds+':>7s} {'sym+':>5s}")
    for imp in IMPULSES:
        for N in [1, 2, 3, 5]:
            # per-symbol top-decile |impulse| events, follow, non-overlap, walk-forward
            sym = {}
            for s in POOL:
                d = data[s]
                sig, y, ev = d["feat"][imp], d["fwd"][N], d["ev"]
                sym[s] = dict(sig=sig, y=y, entry=ev, t1=ev + N)
            all_e = np.concatenate([sym[s]["entry"] for s in POOL])
            edges = np.quantile(all_e, np.linspace(0, 1, N_FOLDS + 1))
            fnet, moves, hits = [], [], []
            sym_pos = np.zeros(len(POOL))
            for k in range(1, N_FOLDS):
                lo, hi = edges[k], edges[k + 1]
                fold = []
                for si, s in enumerate(POOL):
                    d = sym[s]
                    tr = d["entry"] < lo
                    te = (d["entry"] >= lo) & (d["entry"] < hi)
                    ok = np.isfinite(d["sig"]) & np.isfinite(d["y"])
                    if (tr & ok).sum() < 200 or (te & ok).sum() < 20:
                        continue
                    thr = np.nanquantile(np.abs(d["sig"][tr & ok]), 0.90)
                    sel = te & ok & (np.abs(d["sig"]) >= thr)
                    o = np.argsort(d["entry"][sel])
                    e_s, t_s = d["entry"][sel][o], d["t1"][sel][o]
                    keep = greedy_nonoverlap(e_s, t_s)
                    follow = (np.sign(d["sig"][sel]) * d["y"][sel])[o][keep]
                    if len(follow):
                        fold.append(follow)
                        moves.append(np.abs(d["y"][sel][o][keep]))
                        hits.append((follow > 0).astype(float))
                        if np.mean(follow - COST) > 0:
                            sym_pos[si] += 1
                if fold:
                    fnet.append(np.mean(np.concatenate(fold)) - COST)
            if not fnet:
                continue
            mv = np.mean(np.concatenate(moves))
            hit = np.mean(np.concatenate(hits))
            bh = 0.5 + COST / (2 * mv) if mv > 0 else np.nan
            fn = np.array(fnet)
            print(f"  {imp:>16s} {N:>3d} {mv:>7.2f} {bh:>8.3f} {hit:>6.3f} "
                  f"{fn.mean():>+7.2f} {int((fn > 0).sum()):>4d}/{len(fn)} "
                  f"{int((sym_pos >= (N_FOLDS - 1) / 2).sum()):>3d}/5")


if __name__ == "__main__":
    main()
