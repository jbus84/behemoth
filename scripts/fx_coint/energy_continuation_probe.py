"""Find the CONTINUATION (energy-injection) phase that precedes reversion.

Conservation argument: the deviation we fade had to be BUILT — a move out (continuation,
energy injected) precedes the move back (reversion, dissipated). We only ever trade the
dissipation (fade the extended level). This isolates the injection phase using the
move's mechanics on 1000-tick bars:
  position  = ffd_0.1      (how far extended -> potential energy)
  velocity  = ffd_vel5     (kinetic)
  accel     = ffd_accel    (force -> is energy still being injected?)

Regime split (per event, pooled 5 majors, USD-agnostic via sign):
  ACCELERATING : sign(vel)==sign(accel)  -> energy injecting  -> expect CONTINUATION (follow)
  DECELERATING : sign(vel)!=sign(accel)  -> injection stopped  -> expect REVERSION (fade)
crossed with EXTENSION bucket (|position| low / mid / high): the continuation should pay
EARLY (low extension + accelerating), reversion LATE (high extension + decelerating).

For each regime x extension cell, follow the velocity for N bars: mean(sign(vel)*fwd_N).
Positive = continuation pays. Then a tradeable check (net, hit, |move|) on the best cell.

Usage: uv run python scripts/fx_coint/energy_continuation_probe.py
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
N_GRID = [1, 2, 3, 5, 10, 20]
N_EVENTS = 60000
N_FOLDS = 5
COST = 1.0


def build(sym):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    idx = np.arange(warm, n - max(N_GRID) - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    rng = np.random.default_rng(0)
    ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    pos = f["ffd_0.1"][ev]
    vel = f["ffd_vel5"][ev]
    acc = f["ffd_accel"][ev]
    fwd = {N: (logp[ev + N] - logp[ev]) * 1e4 for N in N_GRID}
    return dict(ev=ev, pos=pos, vel=vel, acc=acc, fwd=fwd)


def main():
    data = {s: build(s) for s in POOL}
    pos = np.concatenate([data[s]["pos"] for s in POOL])
    vel = np.concatenate([data[s]["vel"] for s in POOL])
    acc = np.concatenate([data[s]["acc"] for s in POOL])
    fwd = {N: np.concatenate([data[s]["fwd"][N] for s in POOL]) for N in N_GRID}

    ok = np.isfinite(pos) & np.isfinite(vel) & np.isfinite(acc) & (vel != 0)
    accel_aligned = np.sign(vel) == np.sign(acc)
    ext = np.abs(pos)
    e33, e66 = np.nanquantile(ext[ok], [1 / 3, 2 / 3])
    ext_bucket = np.where(ext <= e33, "lo", np.where(ext <= e66, "mid", "hi"))

    print("mean(sign(vel)*fwd_N) bps — >0 = following velocity CONTINUES (energy still moving)")
    print("regime split: ACCEL=energy injecting, DECEL=exhausting; x extension bucket\n")
    print(f"  {'regime':>6s} {'ext':>4s} {'n':>8s} " + " ".join(f"N{N:>4d}" for N in N_GRID))
    cells = []
    for accel, alabel in ((True, "ACCEL"), (False, "DECEL")):
        for eb in ("lo", "mid", "hi"):
            m = ok & (accel_aligned == accel) & (ext_bucket == eb)
            if m.sum() < 500:
                continue
            row = [np.mean(np.sign(vel[m]) * fwd[N][m]) for N in N_GRID]
            cells.append((alabel, eb, m.sum(), row))
            print(f"  {alabel:>6s} {eb:>4s} {m.sum():>8d} " + " ".join(f"{v:>+5.2f}" for v in row))

    # tradeable check on the most-positive (regime,ext,N) continuation cell
    best = None
    for alabel, eb, _nsz, row in cells:
        for ni, N in enumerate(N_GRID):
            if best is None or row[ni] > best[3]:
                best = (alabel, eb, N, row[ni])
    print(f"\nBest continuation cell: {best[0]} ext={best[1]} N={best[2]} gross={best[3]:+.2f} bps")
    _tradeable(data, best[0] == "ACCEL", best[1], best[2], e33, e66)


def _tradeable(data, want_accel, eb, N, e33, e66):
    """Follow velocity in the chosen regime/ext cell; walk-forward net of cost."""
    syms = list(data)
    all_e = np.concatenate([data[s]["ev"] for s in syms])
    edges = np.quantile(all_e, np.linspace(0, 1, N_FOLDS + 1))
    fnet, moves, hits, ntr = [], [], [], 0
    sym_pos = np.zeros(len(syms))
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = data[s]
            ext = np.abs(d["pos"])
            aligned = np.sign(d["vel"]) == np.sign(d["acc"])
            eb_ok = (ext <= e33) if eb == "lo" else ((ext <= e66) & (ext > e33)) if eb == "mid" else (ext > e66)
            te = (d["ev"] >= lo) & (d["ev"] < hi)
            sel = te & (aligned == want_accel) & eb_ok & np.isfinite(d["vel"]) & (d["vel"] != 0) & np.isfinite(d["fwd"][N])
            if sel.sum() < 20:
                continue
            ent, t1 = d["ev"][sel], d["ev"][sel] + N
            o = np.argsort(ent)
            keep = greedy_nonoverlap(ent[o], t1[o])
            pnl = (np.sign(d["vel"][sel]) * d["fwd"][N][sel])[o][keep]
            if len(pnl):
                fold.append(pnl - COST)
                moves.append(np.abs(d["fwd"][N][sel][o][keep]))
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
    print(f"  TRADEABLE follow: n={ntr} |move|={mv:.2f} breakHit={bh:.3f} hit={hit:.3f} "
          f"net={fn.mean() if len(fn) else float('nan'):+.2f} "
          f"folds+={int((fn > 0).sum())}/{len(fn)} sym+={int((sym_pos >= (N_FOLDS - 1) / 2).sum())}/5")


if __name__ == "__main__":
    main()
